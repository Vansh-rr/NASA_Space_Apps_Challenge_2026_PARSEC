from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Sequence

import pandas as pd

from phase1_database import DEMO_DB_PATH, connect_db as _p1_connect
from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_schema import columns_of, create_table_sql

# columns we pull from phase1.observations (superset of overlap_observations)
_P1_COLS = [
    'observation_id', 'sensor_family', 'satellite', 'source_dataset',
    'acq_datetime_utc', 'acq_date', 'daynight',
    'latitude', 'longitude',
    'frp_mw', 'scan_km', 'track_km', 'pixel_area_km2',
]

OVERLAP_COLS = columns_of('overlap_observations')


# none is just for fixing lower and upperbounds when they dont exist
def _overlap_bounds(cfg: Phase2Config, start=None, end=None):
    """Effective date range: intersection of the requested window and the
    overlap period (both MODIS and VIIRS must be operational)."""
    ol_start = cfg.overlap_period.start
    ol_end = cfg.overlap_period.end

    eff_start = max(ol_start, date.fromisoformat(str(start))) if start else ol_start
    if end:
        eff_end = date.fromisoformat(str(end))
        if ol_end:
            eff_end = min(eff_end, ol_end)
    else:
        eff_end = ol_end

    if eff_end and eff_start > eff_end:
        raise ValueError(
            f'Requested window {eff_start}..{end} falls outside '
            f'the overlap period {ol_start}..{ol_end}'
        )
    return eff_start, eff_end


def _fetch_phase1(db_path, region, eff_start, eff_end, satellites, source_datasets, daynight):
    west, south, east, north = region.bbox
    conditions = [
        'latitude  BETWEEN ? AND ?',
        'longitude BETWEEN ? AND ?',
        'acq_date  >= CAST(? AS DATE)',
        'observation_id IS NOT NULL',
    ]
    params = [south, north, west, east, str(eff_start)]

    if eff_end:
        conditions.append('acq_date <= CAST(? AS DATE)')
        params.append(str(eff_end))
    if satellites:
        placeholders = ', '.join('?' for _ in satellites)
        conditions.append(f'satellite IN ({placeholders})')
        params.extend(satellites)
    if source_datasets:
        placeholders = ', '.join('?' for _ in source_datasets)
        conditions.append(f'source_dataset IN ({placeholders})')
        params.extend(source_datasets)
    if daynight is not None:
        if daynight not in ('D', 'N'):
            raise ValueError("daynight must be 'D', 'N' or None")
        conditions.append('daynight = ?')
        params.append(daynight)

    sql = (
        'SELECT ' + ', '.join(_P1_COLS)
        + ' FROM observations WHERE '
        + ' AND '.join(conditions)
        + ' ORDER BY acq_datetime_utc'
    )
    with _p1_connect(db_path) as con:
        return con.execute(sql, params).df()


def _require_both_sensors(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only dates that have at least one MODIS *and* one VIIRS detection
    anywhere in the region, a lightweight overlap check."""
    if df.empty:
        return df
    dates_with_modis = set(df.loc[df['sensor_family'] == 'MODIS', 'acq_date'])
    dates_with_viirs = set(df.loc[df['sensor_family'] == 'VIIRS', 'acq_date'])
    overlap_dates = dates_with_modis & dates_with_viirs
    if not overlap_dates:
        return df.iloc[0:0]
    return df[df['acq_date'].isin(overlap_dates)].copy()


def _add_metadata(df: pd.DataFrame, region_key: str, dataset_version: str) -> pd.DataFrame:
    """Attach the two columns that distinguish overlap_observations from phase1."""
    out = df.copy()
    out['region'] = region_key  # the key (e.g. british_columbia), not the long name
    out['dataset_version'] = dataset_version
    return out[OVERLAP_COLS].reset_index(drop=True)


def extract_overlap(
    *,
    cfg: Phase2Config | None = None,
    db_path=None,
    region: str | None = None,
    start=None,
    end=None,
    satellites: Sequence[str] | None = None,
    source_datasets: Sequence[str] | None = None,
    daynight: str | None = None,
    sample_n: int | None = None,
    require_both_sensors: bool = True,
    seed: int | None = None,
) -> pd.DataFrame:
    """Return an overlap_observations-shaped DataFrame.

    Parameters
    ----------
    cfg             Phase2Config; loads the default config if omitted.
    db_path         Path to Phase 1 DuckDB; uses the default DB_PATH if omitted.
    region          Named region in cfg.regions; uses cfg.default_region if omitted.
    start / end     Date strings or date objects; clipped to the overlap period.
    satellites      Restrict to a subset, e.g. ['Terra', 'S-NPP'].
    source_datasets Restrict by FIRMS product, e.g. ['MODIS_SP'].
    daynight        'D', 'N', or None for both.
    sample_n        Draw this many rows at random (for development samples).
    require_both_sensors
                    Drop dates that have only one sensor family (default True).
    seed            Random seed for sample_n.
    """
    cfg = cfg or load_config()
    region_key = region or cfg.default_region
    reg = cfg.region(region_key)
    dataset_version = cfg.version('overlap')

    eff_start, eff_end = _overlap_bounds(cfg, start, end)

    df = _fetch_phase1(
        db_path, reg, eff_start, eff_end,
        list(satellites) if satellites else None,
        list(source_datasets) if source_datasets else None,
        daynight,
    )

    if require_both_sensors:
        df = _require_both_sensors(df)

    if sample_n is not None:
        if sample_n < 1:
            raise ValueError('sample_n must be a positive integer')
        df = df.sample(n=min(sample_n, len(df)),
                       random_state=seed if seed is not None else cfg.splits.seed)
        df = df.sort_values('acq_datetime_utc')

    return _add_metadata(df, region_key, dataset_version)


def save_overlap(
    df: pd.DataFrame,
    cfg: Phase2Config | None = None,
    region_key: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    cfg = cfg or load_config()
    region_key = region_key or cfg.default_region
    folder = Path(output_dir) if output_dir else cfg.output_dir('overlap')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'overlap_{region_key}.parquet'
    tmp = path.with_suffix('.parquet.part')
    try:
        df.to_parquet(tmp, index=False, engine='pyarrow', compression='zstd')
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    print(f'Saved {len(df):,} overlap observations -> {path}')
    return path


def load_overlap(
    region_key: str | None = None,
    cfg: Phase2Config | None = None,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    cfg = cfg or load_config()
    region_key = region_key or cfg.default_region
    folder = Path(output_dir) if output_dir else cfg.output_dir('overlap')
    path = folder / f'overlap_{region_key}.parquet'
    if not path.exists():
        raise FileNotFoundError(
            f'No overlap Parquet for region {region_key!r} at {path}. '
            f'Run extract_overlap() and save_overlap() first.'
        )
    return pd.read_parquet(path, engine='pyarrow')


def store_overlap_table(df: pd.DataFrame, db_path=None) -> int:
    """Insert into the overlap_observations table (phase1 observations untouched).
    Reruns are safe: rows already stored are skipped."""
    if df.empty:
        return 0
    with _p1_connect(db_path) as con:
        con.execute(create_table_sql('overlap_observations')).fetchall()
        before = con.execute('SELECT COUNT(*) FROM overlap_observations').fetchall()[0][0]
        con.register('new_overlap', df[OVERLAP_COLS])
        try:
            con.execute(
                f'INSERT OR IGNORE INTO overlap_observations ({", ".join(OVERLAP_COLS)}) '
                f'SELECT {", ".join(OVERLAP_COLS)} FROM new_overlap'
            ).fetchall()
        finally:
            con.unregister('new_overlap')
        after = con.execute('SELECT COUNT(*) FROM overlap_observations').fetchall()[0][0]
    print(f'overlap_observations: +{after - before:,} rows ({after:,} total)')
    return after - before


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Extract MODIS-VIIRS overlap dataset (Task 2.2)')
    parser.add_argument('--region', default=None)
    parser.add_argument('--start', default=None)
    parser.add_argument('--end', default=None)
    parser.add_argument('--sample', type=int, default=None, metavar='N')
    parser.add_argument('--db', default=None, help='Phase 1 DuckDB path (default data/fires.duckdb)')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _cfg = load_config(demo_mode=True) if args.demo else load_config()
    # demo reads and writes the separate demo database, never the real one
    _db = args.db or (DEMO_DB_PATH if args.demo else None)
    _region = args.region or _cfg.default_region
    _df = extract_overlap(cfg=_cfg, db_path=_db, region=_region,
                          start=args.start, end=args.end, sample_n=args.sample)
    print(f'Extracted {len(_df):,} rows; sensors: '
          f'{dict(_df["sensor_family"].value_counts().items())}; '
          f'satellites: {dict(_df["satellite"].value_counts().items())}')
    if not _df.empty:
        save_overlap(_df, cfg=_cfg, region_key=_region)
        store_overlap_table(_df, db_path=_db)

