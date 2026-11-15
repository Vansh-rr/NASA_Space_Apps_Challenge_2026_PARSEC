from __future__ import annotations

from typing import Sequence
import numpy as np
import pandas as pd

from phase2.phase2_config import Phase2Config, get_config
from phase2 import phase2_schema

COVERAGE_STATES = ('observed', 'cloudy', 'unavailable', 'unknown')
COVERAGE_PRODUCT_VERSION = '2.8.0'

KEY_COLUMNS = ['cell_id', 'satellite', 'window_start']
COVERAGE_COLUMNS = phase2_schema.columns_of('observation_coverage')
OUTPUT_COLUMNS = [
    'cell_id', 'satellite', 'window_start', 'time_window', 'state', 'observed_fraction', 'source'
]
_TIE_PRIORITY = {'unavailable': 4, 'cloudy': 3, 'unknown': 2, 'observed': 1}


def coverage_version(cfg: Phase2Config | None = None) -> str:
    """Return the dataset version string for observation coverage."""
    cfg = cfg or get_config()
    return f'{COVERAGE_PRODUCT_VERSION}+cfg{cfg.config_version}'


def satellite_available(
    satellite: str, dates: Sequence | pd.Series | np.ndarray, cfg: Phase2Config | None = None
) -> np.ndarray:
    """Return a boolean numpy array indicating if the satellite is available on each date."""
    cfg = cfg or get_config()
    if satellite not in cfg.sensor_availability:
        raise ValueError(f'unknown satellite {satellite!r}')
    period = cfg.sensor_availability[satellite]
    s_dates = pd.to_datetime(pd.Series(dates, dtype='object')).dt.date
    if s_dates.empty:
        return np.array([], dtype=bool)
    avail = s_dates >= period.start
    if period.end is not None:
        avail = avail & (s_dates <= period.end)
    return avail.to_numpy(dtype=bool)


def validate_coverage(coverage: pd.DataFrame) -> None:
    """Validate an observation_coverage DataFrame against schema and domain rules."""
    phase2_schema.check_columns(coverage, COVERAGE_COLUMNS, 'coverage')
    if coverage.empty:
        return

    bad_states = set(coverage['state'].dropna()) - set(COVERAGE_STATES)
    if coverage['state'].isna().any() or bad_states:
        raise ValueError(f'invalid coverage states: {sorted(bad_states)}')

    frac = coverage['fraction'].dropna()
    if (frac < 0.0).any() or (frac > 1.0).any():
        raise ValueError('coverage fraction must be between 0 and 1')

    grouped = coverage.assign(
        window_start=pd.to_datetime(coverage['window_start']).dt.date
    ).groupby(
        ['cell_id', 'satellite', 'window_start', 'time_window', 'dataset_version'],
        dropna=False,
    )['fraction'].sum()
    if (grouped > 1.000001).any():
        raise ValueError('coverage fractions for a single key exceed 1.000001')


def _prepare_keys(keys: pd.DataFrame, cfg: Phase2Config) -> pd.DataFrame:
    """Validate keys, normalize window_start to date, and attach availability flag."""
    phase2_schema.check_columns(keys, KEY_COLUMNS, 'keys')
    if keys.empty:
        return pd.DataFrame(columns=[*KEY_COLUMNS, '_order', '_avail'])

    unknown_sats = set(keys['satellite'].dropna()) - set(cfg.sensor_availability)
    if keys['satellite'].isna().any() or unknown_sats:
        raise ValueError(f'unknown satellite(s): {sorted(unknown_sats)}')

    norm = pd.DataFrame({
        'cell_id': keys['cell_id'].to_numpy(),
        'satellite': keys['satellite'].to_numpy(),
        'window_start': pd.to_datetime(keys['window_start']).dt.date.to_numpy(),
        '_order': np.arange(len(keys)),
    })
    if norm['cell_id'].isna().any() or norm['window_start'].isna().any():
        raise ValueError('keys cannot have missing cell_id or window_start')
    if norm.duplicated(subset=KEY_COLUMNS).any():
        raise ValueError('duplicate keys in input')

    periods = pd.DataFrame([
        {'satellite': sat, '_start': p.start, '_end': p.end}
        for sat, p in cfg.sensor_availability.items()
    ])
    merged = norm.merge(periods, on='satellite', how='left', sort=False)
    avail = merged['window_start'] >= merged['_start']
    has_end = merged['_end'].notna()
    avail = avail & (~has_end | (merged['window_start'] <= merged['_end']))
    norm['_avail'] = avail.to_numpy(dtype=bool)
    return norm


def get_coverage(
    keys: pd.DataFrame,
    coverage: pd.DataFrame | None = None,
    time_window: str = 'day',
    cfg: Phase2Config | None = None,
) -> pd.DataFrame:
    """Resolve observation coverage state and observed fraction for each (cell_id, satellite, window_start) key."""
    cfg = cfg or get_config()
    if coverage is not None:
        validate_coverage(coverage)
        if coverage['dataset_version'].nunique(dropna=False) > 1:
            raise ValueError(
                'coverage contains multiple dataset_version values; filter to one version first'
            )

    norm = _prepare_keys(keys, cfg)
    if norm.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    norm['time_window'] = time_window
    norm['state'] = 'unknown'
    norm['observed_fraction'] = np.nan
    norm['source'] = 'none'

    if coverage is not None and not coverage.empty:
        cov = coverage[coverage['time_window'] == time_window].copy()
        if not cov.empty:
            cov['window_start'] = pd.to_datetime(cov['window_start']).dt.date
            cov['_prio'] = cov['state'].map(_TIE_PRIORITY)
            winners = (
                cov.sort_values(['fraction', '_prio'], ascending=[False, False], na_position='last')
                .drop_duplicates(subset=KEY_COLUMNS, keep='first')
                .rename(columns={'state': '_win_state', 'source': '_win_source'})
                [[*KEY_COLUMNS, '_win_state', '_win_source']]
            )
            obs_frac = (
                cov[cov['state'] == 'observed']
                .groupby(KEY_COLUMNS, as_index=False)['fraction']
                .sum()
                .rename(columns={'fraction': '_obs_frac'})
            )
            norm = norm.merge(winners, on=KEY_COLUMNS, how='left', sort=False)
            norm = norm.merge(obs_frac, on=KEY_COLUMNS, how='left', sort=False)
            has_cov = norm['_win_state'].notna()
            norm.loc[has_cov, 'state'] = norm.loc[has_cov, '_win_state']
            norm.loc[has_cov, 'source'] = norm.loc[has_cov, '_win_source']
            norm.loc[has_cov, 'observed_fraction'] = norm.loc[has_cov, '_obs_frac'].fillna(0.0)

    unavail = ~norm['_avail']
    norm.loc[unavail, 'state'] = 'unavailable'
    norm.loc[unavail, 'observed_fraction'] = 0.0
    norm.loc[unavail, 'source'] = 'sensor_availability'

    norm = norm.sort_values('_order').reset_index(drop=True)
    return norm[OUTPUT_COLUMNS]


def build_coverage_rows(
    keys: pd.DataFrame, time_window: str = 'day', cfg: Phase2Config | None = None
) -> pd.DataFrame:
    """Build fallback observation_coverage table rows using sensor availability and unknown defaults."""
    cfg = cfg or get_config()
    resolved = get_coverage(keys, coverage=None, time_window=time_window, cfg=cfg)
    if resolved.empty:
        return pd.DataFrame(columns=COVERAGE_COLUMNS)

    return pd.DataFrame({
        'cell_id': resolved['cell_id'],
        'satellite': resolved['satellite'],
        'window_start': resolved['window_start'],
        'time_window': resolved['time_window'],
        'state': resolved['state'],
        'fraction': 1.0,
        'source': resolved['source'],
        'dataset_version': coverage_version(cfg),
    })