from __future__ import annotations
from pathlib import Path
import re

import pandas as pd

from phase1_database import DB_PATH, DEMO_DB_PATH, connect_db as _p1_connect
from phase2.phase2_schema import TABLES, columns_of, create_table_sql

# phase 2 tables live in the same DuckDB file as phase 1, next to 'observations'
# phase 1 'observations' is only ever read here, never changed
# demo/synthetic output always goes to the separate demo database


def db_path_for(demo: bool = False, db_path=None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return DEMO_DB_PATH if demo else DB_PATH


def _check_table(con, name: str) -> None:
    """Stop if an existing table has different columns than phase2_schema (needs a migration)."""
    existing = [row[1] for row in con.execute(f"PRAGMA table_info('{name}')").fetchall()]
    if existing and existing != columns_of(name):
        raise RuntimeError(
            f'Table {name!r} in the database has columns {existing}, but phase2_schema expects '
            f'{columns_of(name)}. Back it up and migrate it (see migrate_table); it was not overwritten.'
        )


def connect(db_path=None, demo: bool = False, tables=None):
    """Open the DuckDB file and make sure the Phase 2 tables exist (all, or only `tables`)."""
    con = _p1_connect(db_path_for(demo, db_path))
    try:
        for name in (tables or TABLES):
            if name not in TABLES:
                raise ValueError(f'unknown Phase 2 table {name!r}')
            con.execute(create_table_sql(name)).fetchall()
            _check_table(con, name)
        return con
    except Exception:
        con.close()
        raise


def store(df: pd.DataFrame, table: str, db_path=None, demo: bool = False) -> int:
    """Insert rows into a Phase 2 table. Rows already there (same primary key) are skipped,
    so reruns never create duplicates. Returns the number of new rows."""
    if table not in TABLES:
        raise ValueError(f'unknown Phase 2 table {table!r}')
    cols = columns_of(table)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f'{table}: missing columns {missing}')
    if df.empty:
        return 0
    with connect(db_path, demo, tables=[table]) as con:
        before = con.execute(f'SELECT COUNT(*) FROM {table}').fetchall()[0][0]
        con.register('_new_rows', df[cols])
        try:
            con.execute(
                f'INSERT OR IGNORE INTO {table} ({", ".join(cols)}) '
                f'SELECT {", ".join(cols)} FROM _new_rows'
            ).fetchall()
        finally:
            con.unregister('_new_rows')
        after = con.execute(f'SELECT COUNT(*) FROM {table}').fetchall()[0][0]
    print(f'{table}: +{after - before:,} rows ({after:,} total)')
    return after - before


def load(table: str, db_path=None, demo: bool = False, columns=None,
         where: dict | None = None, limit: int | None = None) -> pd.DataFrame:
    """Read a Phase 2 table. where = {column: value} (value may be a list for IN)."""
    if table not in TABLES:
        raise ValueError(f'unknown Phase 2 table {table!r}')
    allowed = set(columns_of(table))
    cols = columns or columns_of(table)
    bad = [c for c in list(cols) + list((where or {}).keys()) if c not in allowed]
    if bad:
        raise ValueError(f'{table}: unknown columns {bad}')

    conditions, params = [], []
    for col, value in (where or {}).items():
        if isinstance(value, (list, tuple, set)):
            values = list(value)
            conditions.append(f'{col} IN ({", ".join("?" for _ in values)})')
            params.extend(values)
        else:
            conditions.append(f'{col} = ?')
            params.append(value)
    sql = f'SELECT {", ".join(cols)} FROM {table}'
    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError('limit must be a positive integer')
        sql += f' LIMIT {limit}'
    with connect(db_path, demo, tables=[table]) as con:
        return con.execute(sql, params).df()


def delete_version(table: str, dataset_version: str, db_path=None, demo: bool = False) -> int:
    """Remove one dataset version from a table, e.g. before rebuilding it with new settings."""
    if 'dataset_version' not in columns_of(table):
        raise ValueError(f'{table} has no dataset_version column')
    with connect(db_path, demo, tables=[table]) as con:
        before = con.execute(f'SELECT COUNT(*) FROM {table}').fetchall()[0][0]
        con.execute(f'DELETE FROM {table} WHERE dataset_version = ?', [dataset_version]).fetchall()
        after = con.execute(f'SELECT COUNT(*) FROM {table}').fetchall()[0][0]
    print(f'{table}: removed {before - after:,} rows of version {dataset_version}')
    return before - after


def migrate_table(table: str, db_path=None, demo: bool = False) -> str:
    """Rename an outdated table to <table>_old_<n> so connect() can create the new layout."""
    con = _p1_connect(db_path_for(demo, db_path))
    try:
        names = {r[0] for r in con.execute('SHOW TABLES').fetchall()}
        if table not in names:
            return table
        n = 1
        while f'{table}_old_{n}' in names:
            n += 1
        backup = f'{table}_old_{n}'
        con.execute(f'ALTER TABLE {table} RENAME TO {backup}').fetchall()
    finally:
        con.close()
    print(f'{table} renamed to {backup}; the new layout is created on next use')
    return backup


def export_table(table: str, out_path=None, db_path=None, demo: bool = False,
                 where: dict | None = None) -> Path:
    """Write a table to Parquet (for the API/backend or for sharing)."""
    from phase2.phase2_config import load_config
    df = load(table, db_path=db_path, demo=demo, where=where)
    if out_path is None:
        cfg = load_config(demo_mode=demo)
        safe = re.sub(r'[^A-Za-z0-9_-]', '_', table)
        out_path = cfg.output_dir('exports') / f'{safe}.parquet'
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False, engine='pyarrow', compression='zstd')
    print(f'exported {len(df):,} rows of {table} -> {out_path}')
    return out_path


def grid_cells_for_db(grid_cells) -> pd.DataFrame:
    """Turn Kai's build_grid_cells() GeoDataFrame into the grid_cells table layout."""
    out = pd.DataFrame(grid_cells.drop(columns='geometry'))
    out['geometry_wkt'] = grid_cells.geometry.to_wkt()
    return out[columns_of('grid_cells')]


def table_counts(db_path=None, demo: bool = False) -> pd.DataFrame:
    """Row count of 'observations' and every Phase 2 table."""
    with connect(db_path, demo) as con:
        rows = [('observations', con.execute('SELECT COUNT(*) FROM observations').fetchall()[0][0])]
        rows += [(t, con.execute(f'SELECT COUNT(*) FROM {t}').fetchall()[0][0]) for t in TABLES]
    return pd.DataFrame(rows, columns=['table', 'rows'])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Phase 2 database: create tables and show counts (Task 2.15)')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--db', default=None)
    args = parser.parse_args()
    print(f'database: {db_path_for(args.demo, args.db)}')
    print(table_counts(args.db, args.demo).to_string(index=False))