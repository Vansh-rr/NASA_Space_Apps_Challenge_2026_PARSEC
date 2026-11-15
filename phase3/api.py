from __future__ import annotations
import os
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from phase1_database import DB_PATH, DEMO_DB_PATH
from phase1_queries import _where_clause
from phase2.phase2_config import load_config

# backend for the web app (phase 3): B1 app, CORS, read-only database, /health, /regions
#                                    B2 /observations, B3 /activity
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
    expose_headers=['X-Total-Count'],      # so the frontend can read how many rows exist
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


# shared helpers for the endpoints

def region_bbox(region: str) -> tuple:
    cfg = load_config(demo_mode=is_demo())
    if region not in cfg.regions:
        raise HTTPException(404, f'unknown region {region!r}, use one of {sorted(cfg.regions)}')
    return cfg.regions[region].bbox


MONTH = Query('2023-07', pattern=r'^\d{4}-(0[1-9]|1[0-2])$', description='YYYY-MM')


def month_range(month: str) -> tuple[str, str]:
    """'2023-07' -> ('2023-07-01', '2023-07-31')"""
    first = pd.Period(month, freq='M')
    return str(first.start_time.date()), str(first.end_time.date())


def latest_run(con) -> str | None:
    """Newest harmonization run (task 2.13); the harmonized view comes from its predictions."""
    try:
        got = con.execute('SELECT model_run_id FROM model_runs ORDER BY created_at DESC LIMIT 1').fetchall()
    except duckdb.CatalogException:
        return None
    return got[0][0] if got else None


# B2: fire detections for the map

@app.get('/observations')
def observations(response: Response, region: str = 'british_columbia', month: str = MONTH,
                 sensor: Literal['MODIS', 'VIIRS', 'harmonized'] = 'VIIRS',
                 limit: int = Query(10000, ge=1, le=200000), con=Depends(get_db)):
    """Fire detections of one region and month: id, latitude, longitude, frp_mw, observed_at,
    sensor, is_demo. MODIS / VIIRS are raw detections; harmonized = one point per matched MODIS
    detection with the harmonized FRP of the newest model run. X-Total-Count = rows before limit."""
    bbox = region_bbox(region)
    start, end = month_range(month)
    if sensor in ('MODIS', 'VIIRS'):
        where, params = _where_clause(bbox, start, end, sensor)
        base = f'''SELECT observation_id AS id, latitude, longitude, frp_mw,
                          acq_datetime_utc AS observed_at, sensor_family AS sensor
                   FROM observations {where}'''
    else:
        run = latest_run(con)
        if run is None:
            response.headers['X-Total-Count'] = '0'
            return []
        where, params = _where_clause(bbox, start, end)
        where = where.replace('longitude', 'o.longitude').replace('latitude', 'o.latitude') \
                     .replace('acq_datetime_utc', 'o.acq_datetime_utc')
        base = f'''SELECT p.unit_id AS id, o.latitude, o.longitude, p.predicted_value AS frp_mw,
                          o.acq_datetime_utc AS observed_at, 'harmonized' AS sensor
                   FROM model_predictions p
                   JOIN (SELECT DISTINCT match_group_id, modis_observation_id, region
                         FROM matched_observations) mt ON mt.match_group_id = p.unit_id
                   JOIN observations o ON o.observation_id = mt.modis_observation_id
                   {where} {'AND' if where else 'WHERE'} p.model_run_id = ? AND mt.region = ?'''
        params = params + [run, region]
    total = con.execute(f'SELECT COUNT(*) FROM ({base})', params).fetchall()[0][0]
    response.headers['X-Total-Count'] = str(total)
    out = rows(con, f'{base} ORDER BY observed_at, id LIMIT ?', params + [limit])
    for r in out:
        r['is_demo'] = is_demo()
        r['observed_at'] = pd.Timestamp(r['observed_at']).isoformat()
    return out


# B3: fire activity calendar (year x month)

DAY = r'^\d{4}-\d{2}-\d{2}$'


@app.get('/activity')
def activity_matrix(region: str = 'british_columbia',
                    start: str | None = Query(None, pattern=DAY, description='YYYY-MM-DD (default: all)'),
                    end: str | None = Query(None, pattern=DAY, description='YYYY-MM-DD, included'),
                    sensor: Literal['MODIS', 'VIIRS', 'harmonized'] = 'VIIRS', con=Depends(get_db)):
    """Monthly detection count, summed and mean FRP per year/month cell. Months without a row
    have no data downloaded or no detections (not automatically zero fires).
    harmonized = matched MODIS detections with the harmonized FRP of the newest model run."""
    bbox = region_bbox(region)
    if sensor in ('MODIS', 'VIIRS'):
        where, params = _where_clause(bbox, start, end, sensor)
        sql = f'''SELECT year(acq_datetime_utc) AS year, month(acq_datetime_utc) AS month,
                         COUNT(*) AS detections, SUM(frp_mw) AS sum_frp_mw, AVG(frp_mw) AS mean_frp_mw
                  FROM observations {where} GROUP BY 1, 2 ORDER BY 1, 2'''
    else:
        run = latest_run(con)
        if run is None:
            return []
        where, params = _where_clause(bbox, start, end)
        where = where.replace('longitude', 'o.longitude').replace('latitude', 'o.latitude') \
                     .replace('acq_datetime_utc', 'o.acq_datetime_utc')
        sql = f'''SELECT year(o.acq_datetime_utc) AS year, month(o.acq_datetime_utc) AS month,
                         COUNT(*) AS detections, SUM(p.predicted_value) AS sum_frp_mw,
                         AVG(p.predicted_value) AS mean_frp_mw
                  FROM model_predictions p
                  JOIN (SELECT DISTINCT match_group_id, modis_observation_id, region
                        FROM matched_observations) mt ON mt.match_group_id = p.unit_id
                  JOIN observations o ON o.observation_id = mt.modis_observation_id
                  {where} {'AND' if where else 'WHERE'} p.model_run_id = ? AND mt.region = ?
                  GROUP BY 1, 2 ORDER BY 1, 2'''
        params = params + [run, region]
    out = rows(con, sql, params)
    for r in out:
        r['sensor'] = sensor
        r['year'], r['month'], r['detections'] = int(r['year']), int(r['month']), int(r['detections'])
    return out


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('phase3.api:app', host='0.0.0.0', port=8000, reload=True)