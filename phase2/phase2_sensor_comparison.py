from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_database import connect, store
from phase2.phase2_schema import columns_of

# raw sensor comparison and diagnostics (task 2.11)
# describes how MODIS and VIIRS disagree BEFORE any harmonization (not a harmonization method):
#   detections   counts, FRP, brightness temperature, pixel size per satellite / day-night / month
#   matching     how many detections were matched, unmatched and why
#   pairs        one MODIS vs one VIIRS pixel (biased: a MODIS pixel covers ~5 VIIRS pixels)
#   groups       one MODIS vs the SUM of its VIIRS pixels (the fair comparison)

SUMMARY_COLS = columns_of('sensor_comparison_summary')

# columns we pull from phase1.observations for each sensor
_OBS_COLS = [
    'observation_id', 'acq_date',
    'frp_mw', 'delta_bt_k', 'pixel_area_km2', 'mid_ir_bt_k',
    'confidence_numeric', 'confidence_class',
]

PAIR_COLS = [
    'match_group_id', 'region', 'modis_satellite', 'viirs_satellite', 'daynight',
    'acq_date',
    'modis_observation_id', 'modis_frp_mw', 'modis_delta_bt_k',
    'modis_pixel_area_km2', 'modis_mid_ir_bt_k', 'modis_confidence',
    'viirs_observation_id', 'viirs_frp_mw', 'viirs_delta_bt_k',
    'viirs_pixel_area_km2', 'viirs_mid_ir_bt_k', 'viirs_confidence',
    'distance_km', 'time_diff_minutes', 'n_viirs_in_group',
    'log_frp_modis', 'log_frp_viirs', 'log_frp_ratio',
    'dataset_version',
]

_F0_MW = 1.0  # reference power, keeps log dimensionless


# helpers
def _safe_log(series: pd.Series) -> pd.Series:
    v = pd.to_numeric(series, errors='coerce')
    return np.log(v.where(v > 0) / _F0_MW)


def _confidence_label(numeric: pd.Series, categorical: pd.Series) -> pd.Series:
    """Single confidence column: numeric for MODIS (0-100), category for VIIRS."""
    num = pd.to_numeric(numeric, errors='coerce')
    # object dtype so numbers and words ('nominal', 'low', 'high') can share one column
    return num.astype(object).where(num.notna(), categorical.astype(object))


def _frp_magnitude_bin(frp: pd.Series) -> pd.Series:
    """Bin MODIS FRP into four order-of-magnitude classes."""
    bins = [0, 10, 100, 1_000, np.inf]
    labels = ['<10 MW', '10-100 MW', '100-1000 MW', '>1000 MW']
    return pd.cut(frp, bins=bins, labels=labels, right=False)


# build_comparison_pairs
def build_comparison_pairs(matched: pd.DataFrame, obs_df: pd.DataFrame) -> pd.DataFrame:
    """Join matched_observations with Phase 1 observation data.
    One row per matched (MODIS, VIIRS) pair. Pairs where either FRP is missing or not
    positive get NaN log columns but are kept so completeness can still be counted."""
    if matched.empty:
        return pd.DataFrame(columns=PAIR_COLS)

    required_matched = {'match_group_id', 'region', 'modis_observation_id',
                        'viirs_observation_id', 'modis_satellite', 'viirs_satellite',
                        'daynight', 'distance_km', 'time_diff_minutes',
                        'n_viirs_in_group', 'dataset_version'}
    missing = required_matched - set(matched.columns)
    if missing:
        raise ValueError(f'matched is missing columns: {sorted(missing)}')
    missing_obs = {'observation_id', 'frp_mw'} - set(obs_df.columns)
    if missing_obs:
        raise ValueError(f'obs_df is missing columns: {sorted(missing_obs)}')

    obs = obs_df.copy()
    for col in _OBS_COLS:
        if col not in obs.columns:
            obs[col] = np.nan
    obs = obs[_OBS_COLS].drop_duplicates('observation_id').set_index('observation_id')
    m = matched.copy()

    # MODIS side
    m_obs = obs.reindex(m['modis_observation_id'].to_numpy())
    m['acq_date'] = m_obs['acq_date'].to_numpy()
    m['modis_frp_mw'] = m_obs['frp_mw'].to_numpy()
    m['modis_delta_bt_k'] = m_obs['delta_bt_k'].to_numpy()
    m['modis_pixel_area_km2'] = m_obs['pixel_area_km2'].to_numpy()
    m['modis_mid_ir_bt_k'] = m_obs['mid_ir_bt_k'].to_numpy()
    m['modis_confidence'] = _confidence_label(m_obs['confidence_numeric'], m_obs['confidence_class']).to_numpy()

    # VIIRS side
    v_obs = obs.reindex(m['viirs_observation_id'].to_numpy())
    m['viirs_frp_mw'] = v_obs['frp_mw'].to_numpy()
    m['viirs_delta_bt_k'] = v_obs['delta_bt_k'].to_numpy()
    m['viirs_pixel_area_km2'] = v_obs['pixel_area_km2'].to_numpy()
    m['viirs_mid_ir_bt_k'] = v_obs['mid_ir_bt_k'].to_numpy()
    m['viirs_confidence'] = _confidence_label(v_obs['confidence_numeric'], v_obs['confidence_class']).to_numpy()

    # log-FRP columns: y = log(FRP/F0)
    m['log_frp_modis'] = _safe_log(pd.Series(m['modis_frp_mw']))
    m['log_frp_viirs'] = _safe_log(pd.Series(m['viirs_frp_mw']))
    m['log_frp_ratio'] = m['log_frp_viirs'] - m['log_frp_modis']  # log(V/M)
    return m[PAIR_COLS].reset_index(drop=True)


# compute_comparison_stats
def compute_comparison_stats(pairs: pd.DataFrame,
                             by: Sequence[str] = ('modis_satellite', 'viirs_satellite', 'daynight'),
                             frp_magnitude_bins: bool = True) -> pd.DataFrame:
    """Disagreement statistics per group (works on pairs or on group_view(groups)):
    n_pairs, n_frp_both, frp_completeness, log_bias (VIIRS relative to MODIS), log_rmse,
    log_mae, pearson_r of log FRP, frp_ratio_median (VIIRS / MODIS), delta_bt_bias_k,
    n_viirs_mean."""
    if pairs.empty:
        return pd.DataFrame()
    df = pairs.copy()
    if frp_magnitude_bins and 'frp_magnitude' not in df.columns:
        df['frp_magnitude'] = _frp_magnitude_bin(pd.to_numeric(df['modis_frp_mw'], errors='coerce')).astype(str)
    group_cols = [c for c in by if c in df.columns]

    def _stats(g: pd.DataFrame) -> pd.Series:
        n_pairs = len(g)
        sub = g[g['log_frp_modis'].notna() & g['log_frp_viirs'].notna()]
        n_frp = len(sub)
        log_bias = log_rmse = log_mae = r = np.nan
        if n_frp:
            diff = sub['log_frp_ratio']
            log_bias, log_rmse, log_mae = diff.mean(), np.sqrt((diff ** 2).mean()), diff.abs().mean()
        if n_frp > 1 and sub['log_frp_modis'].std() > 0 and sub['log_frp_viirs'].std() > 0:
            r = np.corrcoef(sub['log_frp_modis'], sub['log_frp_viirs'])[0, 1]

        m_frp = pd.to_numeric(g['modis_frp_mw'], errors='coerce')
        v_frp = pd.to_numeric(g['viirs_frp_mw'], errors='coerce')
        ok = (m_frp > 0) & (v_frp > 0)
        m_dbt = pd.to_numeric(g['modis_delta_bt_k'], errors='coerce')
        v_dbt = pd.to_numeric(g['viirs_delta_bt_k'], errors='coerce')
        both = m_dbt.notna() & v_dbt.notna()
        return pd.Series({
            'n_pairs': n_pairs, 'n_frp_both': n_frp,
            'frp_completeness': n_frp / n_pairs if n_pairs else np.nan,
            'log_bias': log_bias, 'log_rmse': log_rmse, 'log_mae': log_mae, 'pearson_r': r,
            'frp_ratio_median': (v_frp[ok] / m_frp[ok]).median(),
            'delta_bt_bias_k': (v_dbt[both] - m_dbt[both]).mean() if both.any() else np.nan,
            'n_viirs_mean': g['n_viirs_in_group'].mean(),
        })

    if group_cols:
        return df.groupby(group_cols, observed=True)[list(df.columns)].apply(_stats).reset_index()
    return _stats(df).to_frame().T.reset_index(drop=True)


# aggregate per match group (sum VIIRS FRP within group)
def aggregate_groups(pairs: pd.DataFrame) -> pd.DataFrame:
    """Collapse one-to-many pairs to one row per match group (MODIS vs summed VIIRS)."""
    if pairs.empty:
        return pd.DataFrame()
    agg = pairs.groupby('match_group_id', sort=False).agg(
        region=('region', 'first'),
        modis_satellite=('modis_satellite', 'first'),
        viirs_satellite=('viirs_satellite', 'first'),
        daynight=('daynight', 'first'),
        acq_date=('acq_date', 'first'),
        modis_observation_id=('modis_observation_id', 'first'),
        modis_frp_mw=('modis_frp_mw', 'first'),
        modis_delta_bt_k=('modis_delta_bt_k', 'first'),
        modis_pixel_area_km2=('modis_pixel_area_km2', 'first'),
        viirs_frp_sum_mw=('viirs_frp_mw', 'sum'),
        viirs_frp_max_mw=('viirs_frp_mw', 'max'),
        viirs_delta_bt_mean_k=('viirs_delta_bt_k', 'mean'),
        viirs_pixel_area_sum_km2=('viirs_pixel_area_km2', 'sum'),
        n_viirs=('viirs_observation_id', 'count'),
        distance_km_mean=('distance_km', 'mean'),
        time_diff_minutes=('time_diff_minutes', 'mean'),
        log_frp_modis=('log_frp_modis', 'first'),
        dataset_version=('dataset_version', 'first'),
    ).reset_index()
    agg['log_frp_viirs_sum'] = _safe_log(agg['viirs_frp_sum_mw'])
    return agg


def group_view(groups: pd.DataFrame) -> pd.DataFrame:
    """Rename aggregate_groups() output so compute_comparison_stats() can use it."""
    g = groups.rename(columns={'viirs_frp_sum_mw': 'viirs_frp_mw', 'log_frp_viirs_sum': 'log_frp_viirs',
                               'viirs_delta_bt_mean_k': 'viirs_delta_bt_k', 'n_viirs': 'n_viirs_in_group'})
    g['log_frp_ratio'] = g['log_frp_viirs'] - g['log_frp_modis']
    return g


def detection_summary(obs: pd.DataFrame, by=('sensor_family', 'satellite', 'daynight')) -> pd.DataFrame:
    """Counts and distributions of FRP, brightness temperature and pixel size per group."""
    o = obs.copy()
    o['month'] = pd.to_datetime(o['acq_datetime_utc']).dt.strftime('%Y-%m')
    return o.groupby(list(by), observed=True).agg(
        n_detections=('observation_id', 'size'),
        frp_mean_mw=('frp_mw', 'mean'), frp_median_mw=('frp_mw', 'median'),
        frp_p90_mw=('frp_mw', lambda x: x.quantile(0.9)), frp_sum_mw=('frp_mw', 'sum'),
        mid_ir_bt_mean_k=('mid_ir_bt_k', 'mean'), delta_bt_mean_k=('delta_bt_k', 'mean'),
        pixel_area_mean_km2=('pixel_area_km2', 'mean'),
        pixel_area_median_km2=('pixel_area_km2', 'median')).reset_index()


def match_summary(obs: pd.DataFrame, matched: pd.DataFrame, unmatched: pd.DataFrame) -> pd.DataFrame:
    """Per satellite: detections, how many were matched, and unmatched counts per reason."""
    ids = set(matched['modis_observation_id']) | set(matched['viirs_observation_id'])
    o = obs.assign(is_matched=obs['observation_id'].isin(ids))
    out = o.groupby('satellite').agg(n_detections=('observation_id', 'size'),
                                     n_matched=('is_matched', 'sum'))
    out['share_matched'] = out['n_matched'] / out['n_detections']
    if not unmatched.empty:
        reasons = unmatched.groupby(['satellite', 'reason']).size().unstack(fill_value=0)
        out = out.join(reasons.add_prefix('unmatched_'), how='left').fillna(0)
    return out.reset_index()


def _long(df: pd.DataFrame, section: str, keys, region: str) -> pd.DataFrame:
    """Wide stats table -> sensor_comparison_summary rows."""
    keys = list(keys)
    d = df.copy()
    d['group_by'] = '+'.join(keys) if keys else 'all'
    d['group_value'] = d[keys].astype(str).agg('|'.join, axis=1) if keys else 'all'
    values = [c for c in d.columns if c not in keys + ['group_by', 'group_value']
              and pd.api.types.is_numeric_dtype(d[c])]
    long = d.melt(id_vars=['group_by', 'group_value'], value_vars=values, var_name='metric')
    long['section'], long['region'] = section, region
    long['value'] = pd.to_numeric(long['value'], errors='coerce').astype(float)
    return long


def load_inputs(region: str, db_path=None, demo=False, cfg: Phase2Config | None = None):
    """Overlap detections (with phase 1 details), matches and unmatched of one region."""
    cfg = cfg or load_config(demo_mode=demo)
    tables = ['overlap_observations', 'matched_observations', 'unmatched_observations']
    with connect(db_path, demo, tables=tables) as con:
        obs = con.execute('''
            SELECT ov.observation_id, ov.region, ov.sensor_family, ov.satellite, ov.daynight,
                   ov.acq_datetime_utc, ov.latitude, ov.longitude, o.acq_date, o.frp_mw,
                   o.delta_bt_k, o.mid_ir_bt_k, o.pixel_area_km2, o.confidence_numeric, o.confidence_class
            FROM overlap_observations ov JOIN observations o USING (observation_id)
            WHERE ov.region = ? AND ov.dataset_version = ?''', [region, cfg.version('overlap')]).df()
        matched = con.execute('SELECT * FROM matched_observations WHERE region = ? AND dataset_version = ?',
                              [region, cfg.version('matching')]).df()
        unmatched = con.execute('SELECT * FROM unmatched_observations WHERE region = ? AND dataset_version = ?',
                                [region, cfg.version('matching')]).df()
    return obs, matched, unmatched


def make_plots(obs, groups, pairs, matched_ids, folder):
    try:
        import matplotlib
    except ImportError:
        print('matplotlib not installed: no plots (pip install matplotlib)')
        return
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # distributions: FRP, brightness temperature, pixel size
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    specs = [('frp_mw', 'FRP (MW, log)', True), ('mid_ir_bt_k', 'mid-IR brightness temperature (K)', False),
             ('pixel_area_km2', 'pixel area (km2)', False)]
    for ax, (col, label, log) in zip(axes, specs):
        for sat, part in obs.groupby('satellite'):
            v = part[col].dropna()
            v = v[v > 0] if log else v
            if v.empty:
                continue
            bins = np.logspace(np.log10(v.min()), np.log10(v.max()), 50) if log else 50
            ax.hist(v, bins=bins, histtype='step', density=True, label=sat)
        ax.set(xscale='log' if log else 'linear', xlabel=label, ylabel='density')
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(folder / 'distributions.png', dpi=150)
    plt.close(fig)

    # one MODIS vs one VIIRS pixel, and one MODIS vs summed VIIRS
    fig, axes = plt.subplots(1, 2, figsize=(10, 5), sharex=True, sharey=True)
    for ax, (df, ycol, title) in zip(axes, [(pairs, 'viirs_frp_mw', 'per pixel pair (biased)'),
                                           (groups, 'viirs_frp_sum_mw', 'per match group (MODIS vs summed VIIRS)')]):
        for dn, part in df.groupby('daynight'):
            ax.scatter(part['modis_frp_mw'], part[ycol], s=4, alpha=0.3, label=dn)
        ax.plot([0.1, 1e4], [0.1, 1e4], 'k--', lw=1)
        ax.set(xscale='log', yscale='log', xlabel='MODIS FRP (MW)', ylabel='VIIRS FRP (MW)', title=title)
    axes[0].legend(title='day/night')
    fig.tight_layout()
    fig.savefig(folder / 'frp_scatter.png', dpi=150)
    plt.close(fig)

    # matched vs unmatched, in numbers and on the map
    o = obs.assign(matched=obs['observation_id'].isin(matched_ids))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    o['status'] = np.where(o['matched'], 'matched', 'unmatched')
    o.groupby(['satellite', 'status']).size().unstack(fill_value=0).plot.bar(ax=axes[0], rot=0)
    axes[0].set(title='matched vs unmatched detections', ylabel='detections', xlabel='')
    for flag, part in o.groupby('matched'):
        axes[1].scatter(part['longitude'], part['latitude'], s=1, alpha=0.3,
                        label='matched' if flag else 'unmatched')
    axes[1].set(title='where detections were matched', xlabel='longitude', ylabel='latitude')
    axes[1].legend(markerscale=8)
    fig.tight_layout()
    fig.savefig(folder / 'matched_unmatched.png', dpi=150)
    plt.close(fig)


def make_comparison(region=None, db_path=None, demo=False, cfg: Phase2Config | None = None,
                    save=True, plots=True) -> pd.DataFrame:
    """Build all comparison summaries; save table rows, CSV/JSON reports and plots."""
    cfg = cfg or load_config(demo_mode=demo)
    region = region or cfg.default_region
    obs, matched, unmatched = load_inputs(region, db_path, demo, cfg)
    if obs.empty or matched.empty:
        raise RuntimeError('no overlap / matches found: run phase2_run.py first')
    pairs = build_comparison_pairs(matched, obs)
    groups = aggregate_groups(pairs)

    parts = [
        _long(detection_summary(obs), 'detections', ['sensor_family', 'satellite', 'daynight'], region),
        _long(detection_summary(obs, ['sensor_family', 'month']), 'detections', ['sensor_family', 'month'], region),
        _long(match_summary(obs, matched, unmatched), 'matching', ['satellite'], region),
        _long(compute_comparison_stats(pairs, by=('modis_satellite', 'daynight'), frp_magnitude_bins=False),
              'pairs', ['modis_satellite', 'daynight'], region),
    ]
    for keys in [('modis_satellite', 'daynight'), ('frp_magnitude',), ('region',)]:
        stats = compute_comparison_stats(group_view(groups), by=keys)
        parts.append(_long(stats, 'groups', list(keys), region))
    summary = pd.concat(parts, ignore_index=True)
    summary['dataset_version'] = cfg.version('comparison')
    summary = summary[SUMMARY_COLS]

    if save:
        store(summary, 'sensor_comparison_summary', db_path=db_path, demo=demo)
        folder = cfg.output_dir('reports', 'sensor_comparison', region)
        summary.to_csv(folder / 'summary.csv', index=False)
        summary.to_json(folder / 'summary.json', orient='records', indent=1)
        if plots:
            ids = set(matched['modis_observation_id']) | set(matched['viirs_observation_id'])
            make_plots(obs, groups, pairs, ids, folder)
        print(f'report: {folder}')
    return summary


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Raw MODIS vs VIIRS comparison (Task 2.11)')
    parser.add_argument('--region', default=None)
    parser.add_argument('--no-plots', action='store_true')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _s = make_comparison(args.region, demo=args.demo, plots=not args.no_plots)
    _w = _s.pivot_table(index=['section', 'group_value'], columns='metric', values='value')
    print('\ndetections per satellite / day-night:')
    print(_w.loc['detections'][['n_detections', 'frp_mean_mw', 'frp_median_mw', 'pixel_area_mean_km2']]
          .dropna().round(2).to_string())
    print('\nmatching per satellite:')
    print(_w.loc['matching'].dropna(axis=1, how='all').round(3).to_string())
    print('\nMODIS vs VIIRS: one pixel (pairs) vs summed VIIRS (groups):')
    cols = ['n_pairs', 'frp_ratio_median', 'log_bias', 'pearson_r']
    print(pd.concat({'pairs': _w.loc['pairs'][cols],
                     'groups': _w.loc['groups'].loc[lambda x: x.index.str.contains(r'\|')][cols]}).round(3).to_string())