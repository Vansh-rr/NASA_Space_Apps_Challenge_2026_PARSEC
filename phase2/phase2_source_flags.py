from __future__ import annotations
from pathlib import Path

import pandas as pd
import yaml

from phase1_storage import ROOT
from phase2.phase2_database import connect, store
from phase2.phase2_schema import columns_of

HISTORY_PATH = ROOT / 'configs' / 'sensor_history.yaml'
FLAG_COLS = columns_of('source_history_flags')

# flags known sensor/product problems (task 2.9) without deleting anything:
#   - time periods with outages or bad calibration (configs/sensor_history.yaml)
#   - non-vegetation hot spots (volcanoes, industry, offshore) from the FIRMS type field
# the flags live in the source_history_flags table; observations are matched to them on the fly


def load_registry(path=None) -> pd.DataFrame:
    """sensor_history.yaml -> source_history_flags rows (periods + static source types)."""
    path = Path(path) if path is not None else HISTORY_PATH
    with path.open(encoding='utf-8') as f:
        raw = yaml.safe_load(f) or {}

    rows = []
    for p in raw.get('periods', []):
        start, end = pd.Timestamp(p['start']).date(), pd.Timestamp(p['end']).date()
        if start > end:
            raise ValueError(f"{p['flag_id']}: start is after end")
        rows.append({'flag_id': p['flag_id'], 'satellite': p.get('satellite'),
                     'source_dataset': p.get('source_dataset'), 'start_date': start,
                     'end_date': end, 'flag': p['flag'], 'description': p.get('description', '')})
    for code, name in (raw.get('static_source_types') or {}).items():
        rows.append({'flag_id': f'firms_type_{int(code)}', 'satellite': None, 'source_dataset': None,
                     'start_date': None, 'end_date': None, 'flag': 'non_vegetation_source',
                     'description': f'FIRMS type {int(code)}: {name}'})
    reg = pd.DataFrame(rows, columns=FLAG_COLS)
    if reg['flag_id'].duplicated().any():
        raise ValueError('duplicate flag_id in sensor_history.yaml')
    return reg


def flag_observations(obs: pd.DataFrame, registry: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return a copy of obs with history_flags (comma separated flag_ids, '' if none)
    and is_flagged columns. Needs satellite, acq_datetime_utc; uses source_dataset and
    hotspot_type_raw when present."""
    registry = load_registry() if registry is None else registry
    out = obs.copy()
    day = pd.to_datetime(out['acq_datetime_utc'], utc=True).dt.tz_localize(None).dt.normalize()
    hits = pd.Series([[] for _ in range(len(out))], index=out.index)

    for r in registry[registry['start_date'].notna()].itertuples(index=False):
        mask = day.between(pd.Timestamp(r.start_date), pd.Timestamp(r.end_date))
        if r.satellite:
            mask &= out['satellite'].eq(r.satellite)
        if r.source_dataset and 'source_dataset' in out.columns:
            mask &= out['source_dataset'].eq(r.source_dataset)
        for i in out.index[mask]:
            hits[i].append(r.flag_id)

    if 'hotspot_type_raw' in out.columns:
        codes = pd.to_numeric(out['hotspot_type_raw'], errors='coerce')
        for r in registry[registry['flag_id'].str.startswith('firms_type_')].itertuples(index=False):
            code = int(r.flag_id.rsplit('_', 1)[1])
            for i in out.index[codes.eq(code)]:
                hits[i].append(r.flag_id)

    out['history_flags'] = hits.map(lambda h: ','.join(h))
    out['is_flagged'] = out['history_flags'] != ''
    return out


def save_registry(db_path=None, demo=False, path=None) -> int:
    return store(load_registry(path), 'source_history_flags', db_path=db_path, demo=demo)


def flagged_observations(db_path=None, demo=False) -> pd.DataFrame:
    """All phase 1 observations that hit a flag, straight from the database."""
    sql = '''
        SELECT o.observation_id, o.sensor_family, o.satellite, o.source_dataset,
               o.acq_datetime_utc, o.hotspot_type_raw, f.flag_id, f.flag
        FROM observations o
        JOIN source_history_flags f ON
             (f.start_date IS NOT NULL
              AND CAST(o.acq_datetime_utc AS DATE) BETWEEN f.start_date AND f.end_date
              AND (f.satellite IS NULL OR f.satellite = o.satellite)
              AND (f.source_dataset IS NULL OR f.source_dataset = o.source_dataset))
          OR (f.flag_id LIKE 'firms_type_%'
              AND o.hotspot_type_raw = CAST(split_part(f.flag_id, '_', 3) AS INTEGER))
        ORDER BY o.acq_datetime_utc
    '''
    with connect(db_path, demo, tables=['source_history_flags']) as con:
        return con.execute(sql).df()


def product_versions(db_path=None, demo=False) -> pd.DataFrame:
    """Which products / processing versions are in the database, per satellite and period."""
    sql = '''
        SELECT source_dataset, source_version, satellite, COUNT(*) AS detections,
               CAST(MIN(acq_datetime_utc) AS DATE) AS first_day,
               CAST(MAX(acq_datetime_utc) AS DATE) AS last_day
        FROM observations GROUP BY ALL ORDER BY source_dataset, satellite, source_version
    '''
    with connect(db_path, demo, tables=[]) as con:
        return con.execute(sql).df()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Known sensor/product problems (Task 2.9)')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    save_registry(demo=args.demo)
    print(load_registry()[['flag_id', 'satellite', 'start_date', 'end_date', 'flag']].to_string(index=False))
    print('\nproducts in the database:')
    print(product_versions(demo=args.demo).to_string(index=False))
    flagged = flagged_observations(demo=args.demo)
    print(f'\nflagged detections: {len(flagged):,}')
    if not flagged.empty:
        print(flagged.groupby(['flag_id', 'satellite'], dropna=False).size().rename('detections').to_string())
