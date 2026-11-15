from __future__ import annotations

import numpy as np
import pandas as pd

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_database import connect, store
from phase2.phase2_schema import columns_of
from phase2.phase2_source_flags import flag_observations, load_registry

# historical time series (task 2.16)
# raw observed activity per period, satellite and sensor family, kept apart from
# harmonized (model) estimates. a period without detections is only 0 when the satellite
# was flying and not in a known outage; otherwise n_detections stays empty (NULL):
#   observed            detections in the period
#   no_detections       satellite available, nothing detected -> real 0
#   outage              whole period inside a known outage (task 2.9) -> unknown
#   sensor_unavailable  satellite not launched yet / ended -> unknown

WINDOWS = ['day', '8day', 'month', 'year']
HIST_COLS = columns_of('historical_observations')
HARM_COLS = columns_of('historical_harmonized_activity')


def period_start(dates, window: str) -> pd.Series:
    """Start day of the period each date falls in. 8day follows the MODIS 8-day
    composites: periods start on 1 Jan, 9 Jan, 17 Jan, ... every year."""
    d = pd.Series(pd.to_datetime(dates)).dt.tz_localize(None).dt.normalize()
    if window == 'day':
        return d
    if window == '8day':
        year_start = d.dt.to_period('Y').dt.start_time
        return year_start + pd.to_timedelta((d.dt.day_of_year - 1) // 8 * 8, unit='D')
    if window == 'month':
        return d.dt.to_period('M').dt.start_time
    if window == 'year':
        return d.dt.to_period('Y').dt.start_time
    raise ValueError(f'unknown time window {window!r}, use {WINDOWS}')


def period_calendar(start, end, window: str) -> pd.DataFrame:
    """Every period touching [start, end] with how many of its days are inside the range."""
    days = pd.Series(pd.date_range(start, end, freq='D'))
    cal = pd.DataFrame({'day': days, 'period_start': period_start(days, window)})
    return cal.groupby('period_start').agg(days_in_range=('day', 'size'),
                                           first_day=('day', 'min'), last_day=('day', 'max')).reset_index()


def load_observations(region: str, start, end, db_path=None, demo=False,
                      cfg: Phase2Config | None = None) -> pd.DataFrame:
    """Phase 1 detections inside the region box and date range, with history flags."""
    cfg = cfg or load_config(demo_mode=demo)
    west, south, east, north = cfg.region(region).bbox
    sql = '''
        SELECT observation_id, sensor_family, satellite, source_dataset, acq_datetime_utc,
               frp_mw, hotspot_type_raw
        FROM observations
        WHERE longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?
          AND CAST(acq_datetime_utc AS DATE) BETWEEN ? AND ?
    '''
    with connect(db_path, demo, tables=[]) as con:
        obs = con.execute(sql, [west, east, south, north, pd.Timestamp(start).date(),
                                pd.Timestamp(end).date()]).df()
    return flag_observations(obs)


def _period_flags(cal: pd.DataFrame, satellites, registry: pd.DataFrame):
    """Per period: comma list of time flags that touch it, and whether an outage covers it all."""
    periods = registry[registry['start_date'].notna() & registry['satellite'].isin(satellites)]
    flags, outage = [], []
    for p in cal.itertuples(index=False):
        touch = periods[(pd.to_datetime(periods['start_date']) <= p.last_day)
                        & (pd.to_datetime(periods['end_date']) >= p.first_day)]
        flags.append(','.join(touch['flag_id']))
        full = touch[(touch['flag'] == 'sensor_outage')
                     & (pd.to_datetime(touch['start_date']) <= p.first_day)
                     & (pd.to_datetime(touch['end_date']) >= p.last_day)]
        # outage only when every satellite of the group is out
        outage.append(len(full) > 0 and set(full['satellite']) >= set(satellites))
    return flags, outage


def _available(cal: pd.DataFrame, satellites, cfg: Phase2Config) -> np.ndarray:
    ok = np.zeros(len(cal), bool)
    for sat in satellites:
        a = cfg.sensor_availability[sat]
        end = pd.Timestamp(a.end) if a.end else pd.Timestamp.max
        ok |= ((cal['last_day'] >= pd.Timestamp(a.start)) & (cal['first_day'] <= end)).to_numpy()
    return ok


def build_history(obs: pd.DataFrame, window: str, region: str, start, end,
                  cfg: Phase2Config | None = None, exclude_flagged: bool = False) -> pd.DataFrame:
    """historical_observations rows: one per period x satellite, plus satellite='all'
    per sensor family (Terra + Aqua = all MODIS)."""
    cfg = cfg or load_config()
    registry = load_registry()
    cal = period_calendar(start, end, window)
    obs = obs.copy()
    obs['period_start'] = period_start(obs['acq_datetime_utc'], window).to_numpy()
    obs['day'] = pd.to_datetime(obs['acq_datetime_utc']).dt.tz_localize(None).dt.normalize()
    if exclude_flagged:
        obs = obs[~obs['is_flagged']]

    rows = []
    for family, ds in [(d.sensor_family, d) for d in cfg.datasets.values()]:
        for sat in ds.satellites + ['all']:
            sats = ds.satellites if sat == 'all' else [sat]
            part = obs[obs['satellite'].isin(sats)]
            stats = part.groupby('period_start').agg(
                n_detections=('observation_id', 'size'), n_flagged=('is_flagged', 'sum'),
                n_days_with_detections=('day', 'nunique'), frp_sum_mw=('frp_mw', 'sum'),
                frp_mean_mw=('frp_mw', 'mean'), frp_p90_mw=('frp_mw', lambda x: x.quantile(0.9)),
                frp_max_mw=('frp_mw', 'max'))
            h = cal.merge(stats, left_on='period_start', right_index=True, how='left')
            flags, outage = _period_flags(cal, sats, registry)
            h['quality_flags'] = flags
            available = _available(cal, sats, cfg)
            has = h['n_detections'].notna().to_numpy()
            h['coverage_state'] = np.select(
                [has, ~available, np.array(outage)],
                ['observed', 'sensor_unavailable', 'outage'], 'no_detections')
            zero = h['coverage_state'] == 'no_detections'           # real zeros only
            h.loc[zero, ['n_detections', 'n_flagged', 'n_days_with_detections']] = 0
            h['sensor_family'], h['satellite'] = family, sat
            rows.append(h)

    out = pd.concat(rows, ignore_index=True)
    for col in ['n_detections', 'n_flagged', 'n_days_with_detections']:
        out[col] = out[col].astype('Int64')
    out['period_start'] = out['period_start'].dt.date
    out['time_window'], out['region'] = window, region
    out['activity_type'] = 'raw_observed'
    out['dataset_version'] = cfg.version('history') + ('+noflagged' if exclude_flagged else '')
    return out[HIST_COLS]


def build_harmonized_history(run_id: str, window: str, db_path=None, demo=False,
                             cfg: Phase2Config | None = None) -> pd.DataFrame:
    """historical_harmonized_activity rows from one model run (task 2.13), summed per period.
    Only covers the units the model predicted (match groups), labelled as estimates."""
    from phase2.phase2_dataset_builder import build_model_input
    from phase2.phase2_model_interface import load_predictions
    from phase2.phase2_validation import split_method_of
    cfg = cfg or load_config(demo_mode=demo)
    pred = load_predictions(run_id, db_path, demo)
    if pred.empty:
        raise RuntimeError(f'run {run_id} has no predictions')
    units = build_model_input(split_method_of(pred['dataset_version'].iloc[0]), db_path, demo, cfg)
    f = pred.merge(units[['unit_id', 'region', 'acq_date']], on='unit_id')
    f['period_start'] = period_start(f['acq_date'], window).dt.date.to_numpy()
    out = f.groupby(['period_start', 'region']).agg(
        n_units=('unit_id', 'size'), source_frp_sum_mw=('source_value', 'sum'),
        harmonized_frp_sum_mw=('predicted_value', 'sum'),
        harmonized_lower_sum_mw=('predicted_lower', lambda x: x.sum(min_count=1)),
        harmonized_upper_sum_mw=('predicted_upper', lambda x: x.sum(min_count=1))).reset_index()
    out['model_run_id'] = run_id
    out['model_name'] = pred['model_name'].iloc[0]
    out['time_window'] = window
    out['activity_type'] = 'harmonized_estimate'
    out['dataset_version'] = cfg.version('history')
    return out[HARM_COLS]


def make_history(region=None, start=None, end=None, windows=None, run_id=None,
                 db_path=None, demo=False, cfg: Phase2Config | None = None, save=True) -> dict:
    """Build (and save) the history for every window. With run_id also the harmonized one.
    Returns {window: historical_observations rows}."""
    cfg = cfg or load_config(demo_mode=demo)
    region = region or cfg.default_region
    start = pd.Timestamp(start or cfg.study_period.start)
    end = pd.Timestamp(end or cfg.study_period.end)
    obs = load_observations(region, start, end, db_path, demo, cfg)
    folder = cfg.output_dir('history', region)

    out = {}
    for w in windows or WINDOWS:
        out[w] = build_history(obs, w, region, start, end, cfg)
        if save:
            store(out[w], 'historical_observations', db_path=db_path, demo=demo)
            out[w].to_parquet(folder / f'observations_{w}.parquet', index=False)
        if run_id:
            harm = build_harmonized_history(run_id, w, db_path, demo, cfg)
            if save:
                store(harm, 'historical_harmonized_activity', db_path=db_path, demo=demo)
                harm.to_parquet(folder / f'harmonized_{w}_{run_id}.parquet', index=False)
    return out


def get_history(window='day', region=None, satellite='all', sensor_family=None,
                db_path=None, demo=False, cfg: Phase2Config | None = None) -> pd.DataFrame:
    """Saved history for the API / frontend later, oldest period first."""
    cfg = cfg or load_config(demo_mode=demo)
    sql = '''SELECT * FROM historical_observations
             WHERE time_window = ? AND region = ? AND satellite = ? AND dataset_version = ?'''
    params = [window, region or cfg.default_region, satellite, cfg.version('history')]
    if sensor_family:
        sql += ' AND sensor_family = ?'
        params.append(sensor_family)
    with connect(db_path, demo, tables=['historical_observations']) as con:
        return con.execute(sql + ' ORDER BY sensor_family, period_start', params).df()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Historical time series (Task 2.16)')
    parser.add_argument('--region', default=None)
    parser.add_argument('--start', default=None)
    parser.add_argument('--end', default=None)
    parser.add_argument('--run', default=None, help='model_run_id to add harmonized history')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _h = make_history(args.region, args.start, args.end, run_id=args.run, demo=args.demo)
    _m = _h['8day']
    print('\n8-day history, all satellites per sensor:')
    print(_m[_m['satellite'] == 'all'][['period_start', 'sensor_family', 'days_in_range', 'coverage_state',
                                        'n_detections', 'frp_sum_mw', 'frp_mean_mw']]
          .round(1).to_string(index=False))
    _d = _h['day']
    print('\ndaily rows by coverage state:')
    print(_d.groupby(['satellite', 'coverage_state']).size().rename('days').to_string())