from __future__ import annotations
import numpy as np
import pandas as pd

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_schema import columns_of, overpass_id as make_overpass_id

OVERPASS_COLS = columns_of('overpass_groups')
PAIR_COLS = ['region', 'daynight', 'modis_overpass_id', 'viirs_overpass_id',
             'modis_satellite', 'viirs_satellite', 'gap_minutes']

# matching is done overpass by overpass: we never compare every MODIS detection
# with every VIIRS detection at once (for BC July 2023 that is ~2.8 billion pairs)


def assign_overpasses(df: pd.DataFrame, cfg: Phase2Config | None = None) -> pd.DataFrame:
    """Return a copy of the overlap DataFrame with an overpass_id column.

    Detections of the same satellite + day/night are one overpass while the gap
    between consecutive detections stays <= cfg.matching.overpass_gap_minutes.
    """
    cfg = cfg or load_config()
    gap = pd.Timedelta(minutes=cfg.matching.overpass_gap_minutes)
    required = {'observation_id', 'region', 'sensor_family', 'satellite',
                'daynight', 'acq_datetime_utc'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f'overlap DataFrame missing columns: {sorted(missing)}')

    out = df.copy()
    if out.empty:
        out['overpass_id'] = pd.Series(dtype='string')
        return out
    out['acq_datetime_utc'] = pd.to_datetime(out['acq_datetime_utc'], utc=True)
    keys = ['region', 'satellite', 'daynight']
    out = out.sort_values(keys + ['acq_datetime_utc'], kind='stable').reset_index(drop=True)

    # a new overpass starts when the group changes or the time gap is too big
    new_group = out[keys].ne(out[keys].shift()).any(axis=1)
    new_pass = new_group | (out['acq_datetime_utc'].diff() > gap)
    pass_no = new_pass.cumsum()
    first_utc = out.groupby(pass_no)['acq_datetime_utc'].transform('first')

    firsts = (pd.DataFrame({'satellite': out['satellite'], 'daynight': out['daynight'],
                            'first': first_utc, 'pass_no': pass_no})
              .drop_duplicates('pass_no'))
    ids = {row.pass_no: make_overpass_id(row.satellite, row.daynight, row.first)
           for row in firsts.itertuples(index=False)}
    out['overpass_id'] = pass_no.map(ids)
    return out


def build_overpass_groups(
    df: pd.DataFrame,
    cfg: Phase2Config | None = None,
    dataset_version: str | None = None,
) -> pd.DataFrame:
    """Return an overpass_groups-shaped DataFrame (one row per satellite pass).

    df may be the overlap DataFrame or the output of assign_overpasses().
    """
    cfg = cfg or load_config()
    dataset_version = dataset_version or cfg.version('matching')
    if df.empty:
        return pd.DataFrame(columns=OVERPASS_COLS)
    if 'overpass_id' not in df.columns:
        df = assign_overpasses(df, cfg)

    ovp = (df.groupby(['overpass_id', 'region', 'sensor_family', 'satellite', 'daynight'],
                      sort=False, dropna=False)
             .agg(start_utc=('acq_datetime_utc', 'min'),
                  end_utc=('acq_datetime_utc', 'max'),
                  n_detections=('observation_id', 'size'))
             .reset_index())
    ovp['dataset_version'] = dataset_version
    return ovp[OVERPASS_COLS].sort_values('start_utc').reset_index(drop=True)


def build_overpass_pairs(ovp: pd.DataFrame, cfg: Phase2Config | None = None) -> pd.DataFrame:
    """MODIS and VIIRS overpasses close enough in time to be compared.

    gap_minutes = 0 when the two passes overlap in time, otherwise the time
    between the end of one and the start of the other. Only pairs with
    gap <= cfg.matching.max_time_diff_minutes are kept.
    """
    cfg = cfg or load_config()
    if ovp.empty:
        return pd.DataFrame(columns=PAIR_COLS)
    keys = ['region', 'daynight'] if cfg.matching.require_same_daynight else ['region']
    cols = ['overpass_id', 'region', 'daynight', 'satellite', 'start_utc', 'end_utc']
    modis = ovp.loc[ovp['sensor_family'] == 'MODIS', cols]
    viirs = ovp.loc[ovp['sensor_family'] == 'VIIRS', cols]
    pairs = modis.merge(viirs, on=keys, suffixes=('_m', '_v'))
    if pairs.empty:
        return pd.DataFrame(columns=PAIR_COLS)

    latest_start = np.maximum(pairs['start_utc_m'], pairs['start_utc_v'])
    earliest_end = np.minimum(pairs['end_utc_m'], pairs['end_utc_v'])
    gap = ((latest_start - earliest_end).dt.total_seconds() / 60).clip(lower=0)
    pairs = pairs.assign(gap_minutes=gap)
    pairs = pairs[pairs['gap_minutes'] <= cfg.matching.max_time_diff_minutes]

    if 'daynight' not in keys:
        pairs = pairs.rename(columns={'daynight_m': 'daynight'})
    out = pairs.rename(columns={
        'overpass_id_m': 'modis_overpass_id', 'overpass_id_v': 'viirs_overpass_id',
        'satellite_m': 'modis_satellite', 'satellite_v': 'viirs_satellite',
    })
    return out[PAIR_COLS].reset_index(drop=True)


# time-window identifiers (day / 8day / month)
def add_time_window_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Add window_day, window_8day (NASA style: day-of-year 1, 9, 17, ...) and window_month."""
    out = df.copy()
    source = out['acq_date'] if 'acq_date' in out.columns else out['acq_datetime_utc']
    day = pd.to_datetime(source, utc=True).dt.tz_localize(None).dt.normalize()
    doy = day.dt.day_of_year
    year_start = day - pd.to_timedelta(doy - 1, unit='D')
    out['window_day'] = day.dt.date
    out['window_8day'] = (year_start + pd.to_timedelta(((doy - 1) // 8) * 8, unit='D')).dt.date
    out['window_month'] = day.dt.to_period('M').dt.start_time.dt.date
    return out


if __name__ == '__main__':
    import argparse
    from phase2.phase2_overlap import load_overlap
    parser = argparse.ArgumentParser(description='Overpass grouping and temporal pairing (Task 2.4)')
    parser.add_argument('--region', default=None)
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _cfg = load_config(demo_mode=True) if args.demo else load_config()
    _obs = assign_overpasses(load_overlap(args.region, cfg=_cfg), _cfg)
    _ovp = build_overpass_groups(_obs, _cfg)
    _pairs = build_overpass_pairs(_ovp, _cfg)
    print(f'{len(_obs):,} detections in {len(_ovp):,} overpasses')
    print(_ovp.groupby('satellite')['n_detections'].agg(['count', 'sum']).rename(
        columns={'count': 'overpasses', 'sum': 'detections'}).to_string())
    print(f'{len(_pairs):,} MODIS-VIIRS overpass pairs within '
          f'{_cfg.matching.max_time_diff_minutes:g} min')
    if not _pairs.empty:
        print(_pairs.groupby('modis_satellite').size().rename('pairs').to_string())
