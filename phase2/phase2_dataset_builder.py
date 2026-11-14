from __future__ import annotations
import pandas as pd

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_database import connect
from phase2.phase2_schema import MODEL_INPUT_REQUIRED, check_columns
from phase2.phase2_splits import make_splits, split_version

# one place for the harmonization team to get model-ready data:
#   rows    = match groups (one MODIS detection + its VIIRS detections)
#   columns = unit_id, unit_type, split, source_value (MODIS FRP),
#             reference_value (summed VIIRS FRP) + numeric features
# features come from task 2.10 (matched_features) when it exists; until then a basic
# set is computed here from the matches so 2.13 / 2.14 can already run.

BASIC_FEATURES_SQL = '''
    SELECT mt.match_group_id,
           any_value(mt.region)           AS region,
           any_value(mt.modis_satellite)  AS modis_satellite,
           any_value(mt.daynight)         AS daynight,
           CAST(any_value(mo.acq_datetime_utc) AS DATE) AS acq_date,
           any_value(mo.frp_mw)           AS modis_frp_mw,
           SUM(vo.frp_mw)                 AS viirs_frp_sum_mw,
           MAX(vo.frp_mw)                 AS viirs_frp_max_mw,
           COUNT(*)                       AS n_viirs,
           any_value(mo.pixel_area_km2)   AS modis_pixel_area_km2,
           SUM(vo.pixel_area_km2)         AS viirs_pixel_area_sum_km2,
           any_value(mo.delta_bt_k)       AS modis_delta_bt_k,
           AVG(vo.delta_bt_k)             AS viirs_delta_bt_mean_k,
           AVG(mt.distance_km)            AS distance_km_mean,
           AVG(mt.time_diff_minutes)      AS time_diff_minutes
    FROM matched_observations mt
    JOIN observations mo ON mo.observation_id = mt.modis_observation_id
    JOIN observations vo ON vo.observation_id = mt.viirs_observation_id
    WHERE mt.dataset_version = ?
    GROUP BY mt.match_group_id
'''


def match_group_features(db_path=None, demo=False, cfg: Phase2Config | None = None) -> pd.DataFrame:
    """Features per match group: task 2.10's matched_features if filled, else the basic set."""
    cfg = cfg or load_config(demo_mode=demo)
    with connect(db_path, demo, tables=['matched_observations', 'matched_features']) as con:
        feats = con.execute('SELECT * FROM matched_features WHERE dataset_version = ?',
                            [cfg.version('features')]).df()
        source = 'matched_features'
        if feats.empty:
            feats = con.execute(BASIC_FEATURES_SQL, [cfg.version('matching')]).df()
            source = 'basic'
    feats['feature_source'] = source
    return feats.drop(columns=['dataset_version'], errors='ignore')


def build_model_input(method: str | None = None, db_path=None, demo=False,
                      cfg: Phase2Config | None = None) -> pd.DataFrame:
    """Model-ready table: one row per match group with its split (makes the split if missing)."""
    cfg = cfg or load_config(demo_mode=demo)
    method = method or cfg.splits.default_method
    version = split_version(cfg, method)
    with connect(db_path, demo, tables=['dataset_splits']) as con:
        splits = con.execute(
            "SELECT unit_id, split, group_id FROM dataset_splits "
            "WHERE unit_type = 'match_group' AND dataset_version = ?", [version]).df()
    if splits.empty:
        splits = make_splits(method, db_path, demo, cfg)[['unit_id', 'split', 'group_id']]

    feats = match_group_features(db_path, demo, cfg)
    out = splits.merge(feats, left_on='unit_id', right_on='match_group_id', how='inner')
    out['unit_type'] = 'match_group'
    out['source_value'] = out['modis_frp_mw']          # what gets converted
    out['reference_value'] = out['viirs_frp_sum_mw']   # what it is compared with
    out['split_version'] = version
    check_columns(out, MODEL_INPUT_REQUIRED, 'model input')
    first = MODEL_INPUT_REQUIRED + ['group_id', 'split_version']
    return out[first + [c for c in out.columns if c not in first]].sort_values('unit_id').reset_index(drop=True)


def load_split(name: str, method: str | None = None, db_path=None, demo=False,
               cfg: Phase2Config | None = None) -> pd.DataFrame:
    """Rows of one split: load_split('train'), load_split('test', method='time')."""
    cfg = cfg or load_config(demo_mode=demo)
    if name not in cfg.splits.names:
        raise ValueError(f'unknown split {name!r}, use one of {cfg.splits.names}')
    data = build_model_input(method, db_path, demo, cfg)
    return data[data['split'] == name].reset_index(drop=True)


def export_model_input(method: str | None = None, db_path=None, demo=False,
                       cfg: Phase2Config | None = None) -> dict:
    """Write one Parquet file per split to data/phase2/model_input/<method>/."""
    cfg = cfg or load_config(demo_mode=demo)
    method = method or cfg.splits.default_method
    data = build_model_input(method, db_path, demo, cfg)
    folder = cfg.output_dir('model_input', method)
    paths = {}
    for name in cfg.splits.names:
        paths[name] = folder / f'{name}.parquet'
        data[data['split'] == name].to_parquet(paths[name], index=False)
    return paths


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Model-ready datasets per split (Task 2.12)')
    parser.add_argument('--method', default=None, help='event (default), time, region or random')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _cfg = load_config(demo_mode=True) if args.demo else load_config()
    _paths = export_model_input(args.method, demo=args.demo, cfg=_cfg)
    _data = build_model_input(args.method, demo=args.demo, cfg=_cfg)
    print(f'features from: {_data["feature_source"].iloc[0]} | split version: {_data["split_version"].iloc[0]}')
    print(_data.groupby('split').agg(rows=('unit_id', 'size'),
                                     modis_frp_median=('source_value', 'median'),
                                     viirs_frp_sum_median=('reference_value', 'median'))
          .reindex(_cfg.splits.names).round(1).to_string())
    for name, path in _paths.items():
        print(f'{name}: {path}')
