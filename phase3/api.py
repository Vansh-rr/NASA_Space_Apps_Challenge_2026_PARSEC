from __future__ import annotations
import os
from pathlib import Path

import duckdb
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from phase1_database import DB_PATH, DEMO_DB_PATH
from phase2.phase2_config import load_config

# backend for the web app (phase 3, task B1): app, CORS, read-only database, /health, /regions
# run:   uvicorn phase3.api:app --reload        then open http://localhost:8000/docs
# env:   PARSEC_DB_PATH        other database file (default data/fires.duckdb)
#        PARSEC_DEMO=1         use the demo database instead
#        PARSEC_CORS_ORIGINS   allowed frontend origins, comma separated (default *)

app = FastAPI(title='PARSEC API', version='0.1.0',
              description='MODIS / VIIRS / harmonized fire data for the PARSEC web app')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get('PARSEC_CORS_ORIGINS', '*').split(',')],
    allow_methods=['GET'],
    allow_headers=['*'],
)


def is_demo() -> bool:
    return os.environ.get('PARSEC_DEMO', '') == '1'


def db_path() -> Path:
    if os.environ.get('PARSEC_DB_PATH'):
        return Path(os.environ['PARSEC_DB_PATH'])
    return DEMO_DB_PATH if is_demo() else DB_PATH


def get_db():
    """One read-only connection per request: the API can never change the data."""
    path = db_path()
    if not path.exists():
        raise HTTPException(503, f'database not found: {path.name} (run phase1_run.py and phase2_run.py first)')
    con = duckdb.connect(str(path), read_only=True)
    try:
        con.execute("SET TimeZone = 'UTC'").fetchall()
        yield con
    finally:
        con.close()


def rows(con, sql: str, params=None) -> list[dict]:
    """Run a query and return a list of dicts (JSON friendly) for the endpoints."""
    df = con.execute(sql, params or []).df()
    return df.astype(object).where(df.notna(), None).to_dict(orient='records')


@app.get('/health')
def health():
    """Is the API up, and can it see the database?"""
    path = db_path()
    out = {'status': 'ok', 'database': path.name, 'database_found': path.exists(), 'demo': is_demo()}
    if path.exists():
        with duckdb.connect(str(path), read_only=True) as con:
            out['observations'] = con.execute('SELECT COUNT(*) FROM observations').fetchall()[0][0]
    return out


@app.get('/regions')
def regions():
    """Study regions from configs/phase2.yaml (bbox = west, south, east, north)."""
    cfg = load_config(demo_mode=is_demo())
    return [{'key': key, 'name': r.name, 'bbox': list(r.bbox), 'is_default': key == cfg.default_region}
            for key, r in cfg.regions.items()]


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('phase3.api:app', host='0.0.0.0', port=8000, reload=True)