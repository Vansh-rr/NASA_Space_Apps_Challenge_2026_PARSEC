from __future__ import annotations
 
from typing import Sequence
 
import numpy as np
import pandas as pd
 
from phase2.phase2_schema import columns_of
 
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
    cat = categorical.astype('string')
    return num.where(num.notna(), cat)
 
 
def _frp_magnitude_bin(frp: pd.Series) -> pd.Series:
    """Bin MODIS FRP into four order-of-magnitude classes."""
    bins   = [0, 10, 100, 1_000, np.inf]
    labels = ['<10 MW', '10-100 MW', '100-1000 MW', '>1000 MW']
    return pd.cut(frp, bins=bins, labels=labels, right=False)
 
# build_comparison_pairs
def build_comparison_pairs(
    matched: pd.DataFrame,
    obs_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join matched_observations with Phase 1 observation data.
 
    Parameters
    ----------
    matched     matched_observations-shaped DataFrame.
    obs_df      Phase 1 observations DataFrame (at minimum the matched IDs).
 
    Returns
    -------
    DataFrame with PAIR_COLS, one row per matched (MODIS, VIIRS) pair.
    Pairs where either sensor's FRP is missing/non-positive get NaN log columns
    but are kept in the output so detection-rate stats can still count them.
    """
    if matched.empty:
        return pd.DataFrame(columns=PAIR_COLS)
 
    required_matched = {'match_group_id', 'region', 'modis_observation_id',
                        'viirs_observation_id', 'modis_satellite', 'viirs_satellite',
                        'daynight', 'distance_km', 'time_diff_minutes',
                        'n_viirs_in_group', 'dataset_version'}
    missing = required_matched - set(matched.columns)
    if missing:
        raise ValueError(f'matched is missing columns: {sorted(missing)}')
 
    required_obs = {'observation_id', 'frp_mw'}
    missing_obs = required_obs - set(obs_df.columns)
    if missing_obs:
        raise ValueError(f'obs_df is missing columns: {sorted(missing_obs)}')
 
    # build lookup from obs_df; fill optional columns with NaN if absent
    obs = obs_df.copy()
    for col in _OBS_COLS:
        if col not in obs.columns:
            obs[col] = np.nan
    obs = obs[_OBS_COLS].drop_duplicates('observation_id').set_index('observation_id')
 
    m = matched.copy()
 
    # MODIS side
    m_obs = obs.reindex(m['modis_observation_id'].to_numpy())
    m['acq_date']             = m_obs['acq_date'].to_numpy()
    m['modis_frp_mw']         = m_obs['frp_mw'].to_numpy()
    m['modis_delta_bt_k']     = m_obs['delta_bt_k'].to_numpy()
    m['modis_pixel_area_km2'] = m_obs['pixel_area_km2'].to_numpy()
    m['modis_mid_ir_bt_k']    = m_obs['mid_ir_bt_k'].to_numpy()
    m['modis_confidence']     = _confidence_label(
        m_obs['confidence_numeric'], m_obs['confidence_class']).to_numpy()
 
    # VIIRS side
    v_obs = obs.reindex(m['viirs_observation_id'].to_numpy())
    m['viirs_frp_mw']         = v_obs['frp_mw'].to_numpy()
    m['viirs_delta_bt_k']     = v_obs['delta_bt_k'].to_numpy()
    m['viirs_pixel_area_km2'] = v_obs['pixel_area_km2'].to_numpy()
    m['viirs_mid_ir_bt_k']    = v_obs['mid_ir_bt_k'].to_numpy()
    m['viirs_confidence']     = _confidence_label(
        v_obs['confidence_numeric'], v_obs['confidence_class']).to_numpy()
 
    # log-FRP columns (notebook sec. 5: y = log(FRP/F0))
    m['log_frp_modis'] = _safe_log(pd.Series(m['modis_frp_mw']))
    m['log_frp_viirs'] = _safe_log(pd.Series(m['viirs_frp_mw']))
    m['log_frp_ratio'] = m['log_frp_viirs'] - m['log_frp_modis']  # log(V/M)
 
    return m[PAIR_COLS].reset_index(drop=True)
 
 
# ---------------------------------------------------------------------------
# compute_comparison_stats
# ---------------------------------------------------------------------------
 
def compute_comparison_stats(
    pairs: pd.DataFrame,
    by: Sequence[str] = ('modis_satellite', 'viirs_satellite', 'daynight'),
    frp_magnitude_bins: bool = True,
) -> pd.DataFrame:
    """Summary statistics for the raw sensor comparison.
 
    Parameters
    ----------
    pairs               Output of build_comparison_pairs().
    by                  Grouping variables.  Any subset of:
                          'modis_satellite', 'viirs_satellite', 'daynight',
                          'region', 'frp_magnitude'
    frp_magnitude_bins  Add an 'frp_magnitude' column binned from MODIS FRP
                        before grouping (useful when 'frp_magnitude' in by).
 
    Returns
    -------
    DataFrame with one row per group, columns:
      <by columns>,
      n_pairs           total matched pairs in this group
      n_frp_both        pairs where both sensors reported FRP > 0
      frp_completeness  n_frp_both / n_pairs
      log_bias          mean(log_frp_viirs - log_frp_modis)  — VIIRS relative to MODIS
      log_rmse          sqrt(mean((log_frp_viirs - log_frp_modis)^2))
      log_mae           mean(|log_frp_viirs - log_frp_modis|)
      pearson_r         Pearson correlation of log FRP
      frp_ratio_median  median(viirs_frp_mw / modis_frp_mw)
      delta_bt_bias_k   mean(viirs_delta_bt_k - modis_delta_bt_k)
      n_viirs_mean      mean n_viirs_in_group
    """
    if pairs.empty:
        return pd.DataFrame()
 
    df = pairs.copy()
    if frp_magnitude_bins and 'frp_magnitude' not in df.columns:
        df['frp_magnitude'] = _frp_magnitude_bin(
            pd.to_numeric(df['modis_frp_mw'], errors='coerce')
        ).astype(str)
 
    group_cols = [c for c in by if c in df.columns]
 
    def _stats(g: pd.DataFrame) -> pd.Series:
        n_pairs   = len(g)
        both_frp  = g['log_frp_modis'].notna() & g['log_frp_viirs'].notna()
        sub       = g[both_frp]
        n_frp     = len(sub)
 
        if n_frp > 1:
            diff      = sub['log_frp_ratio']
            log_bias  = diff.mean()
            log_rmse  = np.sqrt((diff ** 2).mean())
            log_mae   = diff.abs().mean()
            r = np.corrcoef(sub['log_frp_modis'], sub['log_frp_viirs'])[0, 1]
        elif n_frp == 1:
            diff     = sub['log_frp_ratio']
            log_bias = diff.mean()
            log_rmse = np.sqrt((diff ** 2).mean())
            log_mae  = diff.abs().mean()
            r        = np.nan
        else:
            log_bias = log_rmse = log_mae = r = np.nan
 
        # FRP ratio in linear space
        m_frp = pd.to_numeric(g['modis_frp_mw'], errors='coerce')
        v_frp = pd.to_numeric(g['viirs_frp_mw'], errors='coerce')
        ratio_valid = (m_frp > 0) & (v_frp > 0)
        frp_ratio_median = (v_frp[ratio_valid] / m_frp[ratio_valid]).median()
 
        # brightness temperature difference bias
        m_dbt = pd.to_numeric(g['modis_delta_bt_k'], errors='coerce')
        v_dbt = pd.to_numeric(g['viirs_delta_bt_k'], errors='coerce')
        dbt_both = m_dbt.notna() & v_dbt.notna()
        dbt_bias = (v_dbt[dbt_both] - m_dbt[dbt_both]).mean() if dbt_both.any() else np.nan
 
        return pd.Series({
            'n_pairs':           n_pairs,
            'n_frp_both':        n_frp,
            'frp_completeness':  n_frp / n_pairs if n_pairs else np.nan,
            'log_bias':          log_bias,
            'log_rmse':          log_rmse,
            'log_mae':           log_mae,
            'pearson_r':         r,
            'frp_ratio_median':  frp_ratio_median,
            'delta_bt_bias_k':   dbt_bias,
            'n_viirs_mean':      g['n_viirs_in_group'].mean(),
        })
 
    if group_cols:
        return df.groupby(group_cols, observed=True).apply(_stats).reset_index()
    else:
        return _stats(df).to_frame().T.reset_index(drop=True)
 
# convenience: aggregate per match group (sum VIIRS FRP within group)
def aggregate_groups(pairs: pd.DataFrame) -> pd.DataFrame:
    """Collapse one-to-many pairs to one row per match group.
 
    Returns a group-level DataFrame suitable for direct model input:
      match_group_id, region, modis_satellite, viirs_satellite, daynight,
      acq_date, modis_observation_id,
      modis_frp_mw, modis_delta_bt_k, modis_pixel_area_km2,
      viirs_frp_sum_mw, viirs_frp_max_mw, viirs_delta_bt_mean_k,
      viirs_pixel_area_sum_km2,
      n_viirs, distance_km_mean, time_diff_minutes,
      log_frp_modis, log_frp_viirs_sum,
      dataset_version
    """
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
        time_diff_minutes=('time_diff_minutes', 'first'),
        log_frp_modis=('log_frp_modis', 'first'),
        dataset_version=('dataset_version', 'first'),
    ).reset_index()
 
    agg['log_frp_viirs_sum'] = _safe_log(agg['viirs_frp_sum_mw'])
    return agg
 
