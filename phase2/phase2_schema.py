from __future__ import annotations
from hashlib import sha256
import json
import pandas as pd

# shared Phase 2 data contract: IDs, table layouts, model input/output
# phase 1 'observations' is never changed, every table below only points to it by observation_id

UNIT_TYPES = ('match_group', 'grid_cell', 'event')
SPLIT_NAMES = ('train', 'validation', 'test')
UNMATCHED_REASONS = ('no_candidate_in_time', 'no_candidate_in_space', 'outside_overlap')


# IDs - same inputs always give the same id

def stable_id(prefix: str, *parts) -> str:
    canonical = json.dumps([str(p) for p in parts], separators=(',', ':'), ensure_ascii=False)
    return f'{prefix}_{sha256(canonical.encode("utf-8")).hexdigest()[:24]}'


def grid_cell_id(cell_size_km, ix: int, iy: int) -> str:
    return f'g{float(cell_size_km):g}km_{int(ix)}_{int(iy)}'


def overpass_id(satellite, daynight, first_utc) -> str:
    return stable_id('ovp', satellite, daynight, pd.Timestamp(first_utc).isoformat())


def match_group_id(modis_observation_id, config_version) -> str:
    # one group per MODIS detection, holding all its matched VIIRS detections
    return stable_id('mg', modis_observation_id, config_version)


def event_id(first_observation_id, method, config_version) -> str:
    return stable_id('ev', first_observation_id, method, config_version)


def model_run_id(model_name, model_version, dataset_version, parameters=None) -> str:
    params = json.dumps(parameters or {}, sort_keys=True, default=str)
    return stable_id('run', model_name, model_version, dataset_version, params)


# tables: name -> (columns {name: duckdb type}, primary key)
# 2.8, 2.9 and 2.10 tables are drafts their owners can change

TABLES = {
    # 2.2 overlap
    'overlap_observations': ({
        'observation_id': 'VARCHAR NOT NULL', 'region': 'VARCHAR NOT NULL',
        'sensor_family': 'VARCHAR NOT NULL', 'satellite': 'VARCHAR NOT NULL',
        'source_dataset': 'VARCHAR', 'acq_datetime_utc': 'TIMESTAMPTZ NOT NULL',
        'daynight': 'VARCHAR', 'latitude': 'DOUBLE NOT NULL', 'longitude': 'DOUBLE NOT NULL',
        'frp_mw': 'DOUBLE', 'scan_km': 'DOUBLE', 'track_km': 'DOUBLE',
        'pixel_area_km2': 'DOUBLE', 'dataset_version': 'VARCHAR NOT NULL',
    }, ('observation_id', 'region', 'dataset_version')),

    # 2.4-2.6 matching
    'overpass_groups': ({
        'overpass_id': 'VARCHAR NOT NULL', 'region': 'VARCHAR NOT NULL',
        'sensor_family': 'VARCHAR NOT NULL', 'satellite': 'VARCHAR NOT NULL',
        'daynight': 'VARCHAR', 'start_utc': 'TIMESTAMPTZ NOT NULL', 'end_utc': 'TIMESTAMPTZ NOT NULL',
        'n_detections': 'INTEGER NOT NULL', 'dataset_version': 'VARCHAR NOT NULL',
    }, ('overpass_id', 'region', 'dataset_version')),
    'match_candidates': ({
        'modis_observation_id': 'VARCHAR NOT NULL', 'viirs_observation_id': 'VARCHAR NOT NULL',
        'region': 'VARCHAR NOT NULL', 'distance_km': 'DOUBLE NOT NULL',
        'distance_limit_km': 'DOUBLE NOT NULL', 'time_diff_minutes': 'DOUBLE NOT NULL',
        'modis_overpass_id': 'VARCHAR', 'viirs_overpass_id': 'VARCHAR',
        'dataset_version': 'VARCHAR NOT NULL',
    }, ('modis_observation_id', 'viirs_observation_id', 'region', 'dataset_version')),
    'matched_observations': ({
        'match_group_id': 'VARCHAR NOT NULL', 'region': 'VARCHAR NOT NULL',
        'modis_observation_id': 'VARCHAR NOT NULL', 'viirs_observation_id': 'VARCHAR NOT NULL',
        'modis_satellite': 'VARCHAR NOT NULL', 'viirs_satellite': 'VARCHAR NOT NULL',
        'daynight': 'VARCHAR', 'distance_km': 'DOUBLE NOT NULL',
        'time_diff_minutes': 'DOUBLE NOT NULL', 'n_viirs_in_group': 'INTEGER NOT NULL',
        'method': 'VARCHAR NOT NULL', 'config_version': 'VARCHAR NOT NULL',
        'dataset_version': 'VARCHAR NOT NULL',
    }, ('match_group_id', 'viirs_observation_id', 'dataset_version')),
    'unmatched_observations': ({
        'observation_id': 'VARCHAR NOT NULL', 'region': 'VARCHAR NOT NULL',
        'sensor_family': 'VARCHAR NOT NULL', 'satellite': 'VARCHAR NOT NULL',
        'acq_datetime_utc': 'TIMESTAMPTZ NOT NULL', 'reason': 'VARCHAR NOT NULL',
        'dataset_version': 'VARCHAR NOT NULL',
    }, ('observation_id', 'region', 'dataset_version')),

    # 2.12 splits (produced by the 2.12 owner, read by 2.13/2.14)
    'dataset_splits': ({
        'unit_id': 'VARCHAR NOT NULL', 'unit_type': 'VARCHAR NOT NULL',
        'split': 'VARCHAR NOT NULL', 'split_method': 'VARCHAR NOT NULL',
        'group_id': 'VARCHAR', 'seed': 'INTEGER', 'dataset_version': 'VARCHAR NOT NULL',
    }, ('unit_id', 'unit_type', 'dataset_version')),

    # 2.13 model interface
    'model_runs': ({
        'model_run_id': 'VARCHAR NOT NULL', 'model_name': 'VARCHAR NOT NULL',
        'model_version': 'VARCHAR NOT NULL', 'target': 'VARCHAR NOT NULL',
        'unit_type': 'VARCHAR NOT NULL', 'dataset_version': 'VARCHAR NOT NULL',
        'parameters': 'JSON', 'is_synthetic': 'BOOLEAN NOT NULL',
        'created_at': 'TIMESTAMPTZ NOT NULL',
    }, ('model_run_id',)),
    'model_predictions': ({
        'model_run_id': 'VARCHAR NOT NULL', 'unit_id': 'VARCHAR NOT NULL',
        'unit_type': 'VARCHAR NOT NULL', 'split': 'VARCHAR',
        'source_value': 'DOUBLE', 'predicted_value': 'DOUBLE',
        'predicted_lower': 'DOUBLE', 'predicted_upper': 'DOUBLE',
    }, ('model_run_id', 'unit_id')),

    # 2.14 validation
    'model_validation_results': ({
        'model_run_id': 'VARCHAR NOT NULL', 'baseline_run_id': 'VARCHAR',
        'split': 'VARCHAR NOT NULL', 'group_by': 'VARCHAR NOT NULL',
        'group_value': 'VARCHAR NOT NULL', 'metric': 'VARCHAR NOT NULL',
        'value': 'DOUBLE', 'baseline_value': 'DOUBLE', 'n': 'INTEGER NOT NULL',
        'created_at': 'TIMESTAMPTZ NOT NULL',
    }, ('model_run_id', 'split', 'group_by', 'group_value', 'metric')),

    # 2.3 grid (Kai's phase2_grid.py columns; geometry kept as WKT text)
    'grid_cells': ({
        'cell_id': 'VARCHAR NOT NULL', 'region_name': 'VARCHAR NOT NULL',
        'cell_size_km': 'DOUBLE NOT NULL', 'ix': 'BIGINT NOT NULL', 'iy': 'BIGINT NOT NULL',
        'centroid_lat': 'DOUBLE', 'centroid_lon': 'DOUBLE', 'area_km2': 'DOUBLE',
        'grid_version': 'VARCHAR NOT NULL', 'geometry_wkt': 'VARCHAR',
    }, ('cell_id', 'grid_version')),
    'grid_observations': ({
        'observation_id': 'VARCHAR NOT NULL', 'cell_id': 'VARCHAR NOT NULL',
        'cell_size_km': 'DOUBLE NOT NULL', 'ix': 'BIGINT NOT NULL', 'iy': 'BIGINT NOT NULL',
        'grid_version': 'VARCHAR NOT NULL',
    }, ('observation_id', 'cell_size_km', 'grid_version')),
    # 2.7 fire events
    'fire_events': ({
        'event_id': 'VARCHAR NOT NULL', 'region': 'VARCHAR NOT NULL',
        'first_seen_utc': 'TIMESTAMPTZ NOT NULL', 'last_seen_utc': 'TIMESTAMPTZ NOT NULL',
        'duration_hours': 'DOUBLE', 'centroid_lat': 'DOUBLE', 'centroid_lon': 'DOUBLE',
        'lat_min': 'DOUBLE', 'lat_max': 'DOUBLE', 'lon_min': 'DOUBLE', 'lon_max': 'DOUBLE',
        'n_detections': 'INTEGER NOT NULL', 'n_modis': 'INTEGER', 'n_viirs': 'INTEGER',
        'sensors': 'VARCHAR', 'satellites': 'VARCHAR',
        'frp_sum_mw': 'DOUBLE', 'frp_mean_mw': 'DOUBLE', 'frp_max_mw': 'DOUBLE',
        'method': 'VARCHAR NOT NULL', 'parameters': 'JSON',
        'dataset_version': 'VARCHAR NOT NULL',
    }, ('event_id', 'dataset_version')),
    'fire_event_observations': ({
        'event_id': 'VARCHAR NOT NULL', 'observation_id': 'VARCHAR NOT NULL',
        'region': 'VARCHAR NOT NULL', 'dataset_version': 'VARCHAR NOT NULL',
    }, ('observation_id', 'region', 'dataset_version')),
    # drafts for other owners (2.8, 2.9, 2.10)
    'observation_coverage': ({
        'cell_id': 'VARCHAR NOT NULL', 'satellite': 'VARCHAR NOT NULL',
        'window_start': 'DATE NOT NULL', 'time_window': 'VARCHAR NOT NULL',
        'state': 'VARCHAR NOT NULL', 'fraction': 'DOUBLE', 'source': 'VARCHAR',
        'dataset_version': 'VARCHAR NOT NULL',
    }, ('cell_id', 'satellite', 'window_start', 'time_window', 'state', 'dataset_version')),
    'source_history_flags': ({
        'flag_id': 'VARCHAR NOT NULL', 'satellite': 'VARCHAR', 'source_dataset': 'VARCHAR',
        'start_date': 'DATE', 'end_date': 'DATE', 'flag': 'VARCHAR NOT NULL',
        'description': 'VARCHAR',
    }, ('flag_id',)),
    'matched_features': ({
        'match_group_id': 'VARCHAR NOT NULL', 'region': 'VARCHAR', 'acq_date': 'DATE',
        'modis_satellite': 'VARCHAR', 'daynight': 'VARCHAR',
        'modis_frp_mw': 'DOUBLE', 'viirs_frp_sum_mw': 'DOUBLE', 'viirs_frp_max_mw': 'DOUBLE',
        'n_viirs': 'INTEGER', 'modis_pixel_area_km2': 'DOUBLE', 'viirs_pixel_area_sum_km2': 'DOUBLE',
        'modis_delta_bt_k': 'DOUBLE', 'viirs_delta_bt_mean_k': 'DOUBLE',
        'distance_km_mean': 'DOUBLE', 'time_diff_minutes': 'DOUBLE',
        'dataset_version': 'VARCHAR NOT NULL',
    }, ('match_group_id', 'dataset_version')),
}


def create_table_sql(name: str) -> str:
    columns, key = TABLES[name]
    lines = [f'    {col} {kind}' for col, kind in columns.items()]
    lines.append(f'    PRIMARY KEY ({", ".join(key)})')
    return f'CREATE TABLE IF NOT EXISTS {name} (\n' + ',\n'.join(lines) + '\n)'


def columns_of(name: str) -> list[str]:
    return list(TABLES[name][0])


# model input/output contract (2.13)
# a model gets one row per unit: these columns + any numeric feature columns
# source_value = the value being converted (e.g. MODIS FRP)
# reference_value = the other sensor's value (e.g. VIIRS FRP), only used for fitting/evaluation
MODEL_INPUT_REQUIRED = ['unit_id', 'unit_type', 'split', 'source_value', 'reference_value']
PREDICTION_COLUMNS = columns_of('model_predictions')


def check_columns(frame: pd.DataFrame, required, what='frame') -> None:
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f'{what} is missing columns: {missing}')


for _name, (_cols, _key) in TABLES.items():
    assert set(_key) <= set(_cols), f'{_name}: primary key not in columns'
