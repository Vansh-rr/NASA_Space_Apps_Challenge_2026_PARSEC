from __future__ import annotations
from pathlib import Path
import re
import duckdb
import pandas as pd
from phase1_schema import OBSERVATION_COLUMNS
from phase1_storage import DATA_DIR, FOLDERS

DB_PATH = DATA_DIR / 'fires.duckdb'
DEMO_DB_PATH = DATA_DIR / 'demo_fires.duckdb'

DUCK_TYPES = {'observation_id': 'VARCHAR PRIMARY KEY','schema_version': 'SMALLINT','sensor_family': 'VARCHAR NOT NULL','instrument': 'VARCHAR NOT NULL','satellite': 'VARCHAR','source_dataset': 'VARCHAR','source_version': 'VARCHAR','acq_datetime_utc': 'TIMESTAMPTZ NOT NULL','acq_date': 'DATE','daynight': 'VARCHAR','latitude': 'DOUBLE NOT NULL','longitude': 'DOUBLE NOT NULL','frp_mw': 'DOUBLE','mid_ir_bt_k': 'DOUBLE','mid_ir_channel': 'VARCHAR','longwave_bt_k': 'DOUBLE','longwave_channel': 'VARCHAR','delta_bt_k': 'DOUBLE','scan_km': 'DOUBLE','track_km': 'DOUBLE','pixel_area_km2': 'DOUBLE','confidence_raw': 'VARCHAR','confidence_scheme': 'VARCHAR','confidence_numeric': 'SMALLINT','confidence_class': 'VARCHAR','hotspot_type_raw': 'SMALLINT','source_record': 'JSON','source_file': 'VARCHAR','ingestion_batch_id': 'VARCHAR','ingested_at': 'TIMESTAMPTZ',}
assert list(DUCK_TYPES) == OBSERVATION_COLUMNS
CREATE_TABLE = 'CREATE TABLE IF NOT EXISTS observations (\n' + ',\n'.join(
    f'    {field} {type_spec}' for field, type_spec in DUCK_TYPES.items()
) + '\n)'
SELECT_COLUMNS = ', '.join(OBSERVATION_COLUMNS)
SELECT_EXPR = ', '.join(
    'CAST(source_record AS JSON) AS source_record' if field == 'source_record'
    else field for field in OBSERVATION_COLUMNS
)


def connect_db(db_path=None):
    """Return a fresh connection"""
    path = Path(db_path) if db_path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute("SET TimeZone = 'UTC'").fetchall()
        con.execute(CREATE_TABLE).fetchall()
        existing = [row[1] for row in con.execute("PRAGMA table_info('observations')").fetchall()]
        if existing != OBSERVATION_COLUMNS:
            raise RuntimeError(
                'Existing DuckDB observations schema differs from the 30-field '
                'contract. Back up and migrate the old database; do not overwrite it.'
            )
        return con
    except Exception:
        con.close()
        raise


def prepare_for_db(frame):
    """Filter only the coordinates/time/identity needed for safe storage."""
    missing = sorted(set(OBSERVATION_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f'Missing standardized columns: {missing}')
    if frame.empty:
        return frame.reindex(columns=OBSERVATION_COLUMNS).copy()

    modis = frame['sensor_family'].eq('MODIS')
    viirs = frame['sensor_family'].eq('VIIRS')
    modis_ok = (
        modis & frame['instrument'].eq('MODIS')
        & frame['satellite'].isin(('Terra', 'Aqua'))
        & frame['confidence_scheme'].eq('numeric_0_100')
        & frame['confidence_numeric'].between(0, 100)
        & frame['confidence_class'].isna()
        & frame['mid_ir_channel'].eq('B21/B22_unspecified')
        & frame['longwave_channel'].eq('B31')
    )
    viirs_ok = (
        viirs & frame['instrument'].eq('VIIRS')
        & frame['satellite'].isin(('S-NPP', 'NOAA-20', 'NOAA-21'))
        & frame['confidence_scheme'].eq('categorical_lnh')
        & frame['confidence_class'].isin(('low', 'nominal', 'high'))
        & frame['confidence_numeric'].isna()
        & frame['mid_ir_channel'].eq('I4')
        & frame['longwave_channel'].eq('I5')
    )
    valid = (
        frame['latitude'].between(-90, 90)
        & frame['longitude'].between(-180, 180)
        & frame['acq_datetime_utc'].notna()
        & frame['observation_id'].notna()
        & frame['daynight'].isin(('D', 'N'))
        & frame['source_dataset'].notna()
        & frame['source_version'].notna()
        & frame['schema_version'].ge(1)
        & (frame['frp_mw'].isna() | frame['frp_mw'].ge(0))
        & (frame['mid_ir_bt_k'].isna() | frame['mid_ir_bt_k'].gt(0))
        & (frame['longwave_bt_k'].isna() | frame['longwave_bt_k'].gt(0))
        & (frame['scan_km'].isna() | frame['scan_km'].gt(0))
        & (frame['track_km'].isna() | frame['track_km'].gt(0))
        & (modis_ok | viirs_ok)
    )
    prepared = (frame.loc[valid, OBSERVATION_COLUMNS]
                .drop_duplicates('observation_id', keep='first').copy())
    print(f'Rows retained for database: {len(prepared):,} / {len(frame):,}')
    return prepared


def load_standardized(frame, name, db_path=None, parquet_dir=None):
    """Save one standardized batch and insert only previously unseen IDs.

    The primary key makes reruns idempotent. All SQL results are fully
    consumed before interacting with the same DuckDB connection.
    """
    prepared = prepare_for_db(frame)
    if prepared.empty:
        print(f'{name}: no observations to store')
        return 0
    safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', str(name))
    if not safe_name:
        raise ValueError('Invalid snapshot filename')
    folder = Path(parquet_dir) if parquet_dir is not None else FOLDERS['standardized']
    folder.mkdir(parents=True, exist_ok=True)
    parquet_path = folder / f'{safe_name}.parquet'
    temp_path = folder / f'.{safe_name}.parquet.part'
    try:
        prepared.to_parquet(temp_path, compression='zstd', index=False, engine='pyarrow')
        temp_path.replace(parquet_path)
    finally:
        temp_path.unlink(missing_ok=True)

    with connect_db(db_path) as con:
        before = con.execute('SELECT COUNT(*) FROM observations').fetchall()[0][0]
        con.register('new_rows', prepared)
        try:
            con.execute(
                f'INSERT OR IGNORE INTO observations ({SELECT_COLUMNS}) '
                f'SELECT {SELECT_EXPR} FROM new_rows'
            ).fetchall()
        finally:
            # The previous result is finished even if INSERT returned metadata.
            con.unregister('new_rows')
        after = con.execute('SELECT COUNT(*) FROM observations').fetchall()[0][0]
    added = after - before
    print(f'{name}: +{added:,} inserted ({after:,} total); Parquet: {parquet_path.name}')
    return added
