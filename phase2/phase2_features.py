from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from phase2 import phase2_config
from phase2 import phase2_database
from phase2 import phase2_schema
TABLE_COLUMNS: list[str] = phase2_schema.columns_of('matched_features')
EXTRA_COLUMNS: list[str] = [
    'modis_scan_km',
    'modis_track_km',
    'viirs_scan_km_mean',
    'viirs_track_km_mean',
    'time_gap_minutes_signed',
    'modis_confidence_numeric',
    'n_viirs_with_frp',
]
ALL_COLUMNS: list[str] = TABLE_COLUMNS + EXTRA_COLUMNS

_OBS_COLS = [
    'observation_id',
    'acq_datetime_utc',
    'acq_date',
    'frp_mw',
    'scan_km',
    'track_km',
    'pixel_area_km2',
    'delta_bt_k',
    'confidence_numeric',
]


def build_matched_features(
    matched: pd.DataFrame,
    observations: pd.DataFrame,
    cfg: phase2_config.Phase2Config | None = None,
    dataset_version: str | None = None,
) -> pd.DataFrame:
    """Build one summary feature row per match_group_id from matched pairs and observations."""
    cfg = cfg or phase2_config.load_config()
    dataset_version = dataset_version or cfg.version('features')

    if matched.empty:
        return pd.DataFrame(columns=ALL_COLUMNS)

    obs = observations[_OBS_COLS].drop_duplicates('observation_id')
    known_ids = set(obs['observation_id'])
    missing_modis = set(matched['modis_observation_id']) - known_ids
    missing_viirs = set(matched['viirs_observation_id']) - known_ids
    n_missing = len(missing_modis | missing_viirs)
    if n_missing:
        raise ValueError(
            f'{n_missing} observation_id(s) missing from observations '
            f'(modis={len(missing_modis)}, viirs={len(missing_viirs)})'
        )

    obs = obs.copy()
    obs['acq_datetime_utc'] = pd.to_datetime(obs['acq_datetime_utc'], utc=True)

    modis_obs = obs.rename(columns={
        'observation_id': 'modis_observation_id',
        'acq_datetime_utc': 'modis_time',
        'acq_date': 'acq_date',
        'frp_mw': 'modis_frp_mw',
        'scan_km': 'modis_scan_km',
        'track_km': 'modis_track_km',
        'pixel_area_km2': 'modis_pixel_area_km2',
        'delta_bt_k': 'modis_delta_bt_k',
        'confidence_numeric': 'modis_confidence_numeric',
    })
    viirs_obs = obs.drop(columns=['acq_date', 'confidence_numeric']).rename(columns={
        'observation_id': 'viirs_observation_id',
        'acq_datetime_utc': 'viirs_time',
        'frp_mw': 'viirs_frp_mw',
        'scan_km': 'viirs_scan_km',
        'track_km': 'viirs_track_km',
        'pixel_area_km2': 'viirs_pixel_area_km2',
        'delta_bt_k': 'viirs_delta_bt_k',
    })

    joined = (
        matched[[
            'match_group_id',
            'region',
            'modis_observation_id',
            'viirs_observation_id',
            'modis_satellite',
            'daynight',
            'distance_km',
        ]]
        .merge(modis_obs, on='modis_observation_id', how='left')
        .merge(viirs_obs, on='viirs_observation_id', how='left')
    )

    signed_gap = (joined['viirs_time'] - joined['modis_time']).dt.total_seconds() / 60.0
    joined['time_gap_minutes_signed'] = signed_gap
    joined['time_diff_minutes'] = signed_gap.abs()

    grp = joined.groupby('match_group_id', sort=False)

    out = pd.DataFrame({
        'match_group_id': grp['match_group_id'].first(),
        'region': grp['region'].first(),
        'acq_date': grp['acq_date'].first(),
        'modis_satellite': grp['modis_satellite'].first(),
        'daynight': grp['daynight'].first(),
        'modis_frp_mw': grp['modis_frp_mw'].first(),
        'viirs_frp_sum_mw': grp['viirs_frp_mw'].sum(min_count=1),
        'viirs_frp_max_mw': grp['viirs_frp_mw'].max(),
        'n_viirs': grp.size().astype(np.int64),
        'modis_pixel_area_km2': grp['modis_pixel_area_km2'].first(),
        'viirs_pixel_area_sum_km2': grp['viirs_pixel_area_km2'].sum(min_count=1),
        'modis_delta_bt_k': grp['modis_delta_bt_k'].first(),
        'viirs_delta_bt_mean_k': grp['viirs_delta_bt_k'].mean(),
        'distance_km_mean': grp['distance_km'].mean(),
        'time_diff_minutes': grp['time_diff_minutes'].mean(),
        'dataset_version': dataset_version,
        'modis_scan_km': grp['modis_scan_km'].first(),
        'modis_track_km': grp['modis_track_km'].first(),
        'viirs_scan_km_mean': grp['viirs_scan_km'].mean(),
        'viirs_track_km_mean': grp['viirs_track_km'].mean(),
        'time_gap_minutes_signed': grp['time_gap_minutes_signed'].mean(),
        'modis_confidence_numeric': grp['modis_confidence_numeric'].first(),
        'n_viirs_with_frp': grp['viirs_frp_mw'].count().astype(np.int64),
    }).reset_index(drop=True)

    return out[ALL_COLUMNS]


def load_feature_inputs(
    db_path: str | Path | None = None,
    demo: bool = False,
    region: str | None = None,
    cfg: phase2_config.Phase2Config | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read matched_observations and the referenced observations rows in read-only mode."""
    cfg = cfg or (phase2_config.load_config(demo_mode=True) if demo else phase2_config.load_config())
    path = phase2_database.db_path_for(demo, db_path)
    matching_version = cfg.version('matching')

    where_sql = 'WHERE dataset_version = ?'
    params: list[str] = [matching_version]
    if region is not None:
        where_sql += ' AND region = ?'
        params.append(region)

    with duckdb.connect(str(path), read_only=True) as con:
        matched = con.execute(
            f'SELECT * FROM matched_observations {where_sql}',
            params,
        ).df()
        if matched.empty:
            observations = con.execute(
                f'SELECT {", ".join(_OBS_COLS)} FROM observations WHERE 1 = 0'
            ).df()
        else:
            obs_sql = (
                f'SELECT {", ".join(_OBS_COLS)} FROM observations '
                f'WHERE observation_id IN ('
                f'  SELECT modis_observation_id FROM matched_observations {where_sql}'
                f'  UNION'
                f'  SELECT viirs_observation_id FROM matched_observations {where_sql}'
                f')'
            )
            observations = con.execute(obs_sql, params + params).df()

    return matched, observations


def run_features(
    db_path: str | Path | None = None,
    demo: bool = False,
    region: str | None = None,
    cfg: phase2_config.Phase2Config | None = None,
) -> pd.DataFrame:
    """Load inputs, compute per-group features, store to DuckDB, and write Parquet."""
    cfg = cfg or (phase2_config.load_config(demo_mode=True) if demo else phase2_config.load_config())
    matched, observations = load_feature_inputs(
        db_path=db_path, demo=demo, region=region, cfg=cfg
    )
    features = build_matched_features(matched, observations, cfg=cfg)
    phase2_database.store(features, 'matched_features', db_path, demo)

    out_path = cfg.output_dir('features') / 'matched_features.parquet'
    features.to_parquet(out_path, index=False)
    print(f'matched_features: {len(features):,} rows -> {out_path}')
    return features


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Per-match-group feature table for PARSEC Phase 2 (Task 2.10)'
    )
    parser.add_argument('--region', default=None)
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    run_features(demo=args.demo, region=args.region)

