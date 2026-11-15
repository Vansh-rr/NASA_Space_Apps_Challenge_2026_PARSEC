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
from phase2.model_preview import PreviewStore
from phase2.phase2_config import load_config

# backend for the web app (phase 3): B1 app, CORS, read-only database, /health, /regions
#                                    B2 /observations, B3 /activity, B5 /comparison, B6/B7 /history
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
def health(response: Response):
    path = db_path()

    result = {
        "status": "unhealthy",
        "database": path.name,
        "database_found": path.exists(),
        "database_connected": False,
        "demo": is_demo()
    }

    if not path.exists():
        response.status_code = 503
        return result

    try:
        with duckdb.connect(str(path), read_only=True) as con:
            count = con.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0]

            result["status"] = "ok"
            result["database_connected"] = True
            result["observations"] = count

    except Exception:
        response.status_code = 503

    return result

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


def points_sql(con, region: str, start: str | None, end: str | None, sensor: str):
    """SQL + params selecting id, latitude, longitude, frp_mw, observed_at, sensor for one sensor.
    harmonized = one point per matched MODIS detection with the newest model run's FRP.
    Returns None when harmonized is asked but no model run exists yet."""
    bbox = region_bbox(region)
    if sensor in ('MODIS', 'VIIRS'):
        where, params = _where_clause(bbox, start, end, sensor)
        return f'''SELECT observation_id AS id, latitude, longitude, frp_mw,
                           acq_datetime_utc AS observed_at, sensor_family AS sensor
                    FROM observations {where}''', params
    run = latest_run(con)
    if run is None:
        return None
    where, params = _where_clause(bbox, start, end)
    where = where.replace('longitude', 'o.longitude').replace('latitude', 'o.latitude') \
                 .replace('acq_datetime_utc', 'o.acq_datetime_utc')
    return f'''SELECT p.unit_id AS id, o.latitude, o.longitude, p.predicted_value AS frp_mw,
                       o.acq_datetime_utc AS observed_at, 'harmonized' AS sensor
                FROM model_predictions p
                JOIN (SELECT DISTINCT match_group_id, modis_observation_id, region
                      FROM matched_observations) mt ON mt.match_group_id = p.unit_id
                JOIN observations o ON o.observation_id = mt.modis_observation_id
                {where} {'AND' if where else 'WHERE'} p.model_run_id = ? AND mt.region = ?''', \
           params + [run, region]


def as_points(out: list[dict]) -> list[dict]:
    for r in out:
        r['is_demo'] = is_demo()
        r['observed_at'] = pd.Timestamp(r['observed_at']).isoformat()
    return out


# B2: fire detections for the map

@app.get('/observations')
def observations(response: Response, region: str = 'british_columbia', month: str = MONTH,
                 sensor: Literal['MODIS', 'VIIRS', 'harmonized'] = 'VIIRS',
                 limit: int = Query(10000, ge=1, le=200000), con=Depends(get_db)):
    """Fire detections of one region and month: id, latitude, longitude, frp_mw, observed_at,
    sensor, is_demo. MODIS / VIIRS are raw detections; harmonized = one point per matched MODIS
    detection with the harmonized FRP of the newest model run. X-Total-Count = rows before limit."""
    q = points_sql(con, region, *month_range(month), sensor)
    if q is None:
        response.headers['X-Total-Count'] = '0'
        return []
    base, params = q
    total = con.execute(f'SELECT COUNT(*) FROM ({base})', params).fetchall()[0][0]
    response.headers['X-Total-Count'] = str(total)
    return as_points(rows(con, f'{base} ORDER BY observed_at, id LIMIT ?', params + [limit]))


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


# B5: MODIS vs VIIRS vs harmonized for one month

@app.get('/comparison')
def comparison(region: str = 'british_columbia', month: str = MONTH,
               sample: int = Query(200, ge=0, le=5000), con=Depends(get_db)):
    """Per sensor (MODIS, VIIRS, harmonized): detection count, mean FRP, active days,
    daily detection counts / FRP, and a fixed random sample of detection points for the map."""
    start, end = month_range(month)
    out = []
    for sensor in ('MODIS', 'VIIRS', 'harmonized'):
        q = points_sql(con, region, start, end, sensor)
        if q is None:
            out.append({'sensor': sensor, 'detections': 0, 'mean_frp_mw': None, 'active_days': 0,
                        'daily': [], 'sample': [], 'note': 'no harmonization run yet'})
            continue
        base, params = q
        n, mean_frp, days = con.execute(
            f'SELECT COUNT(*), AVG(frp_mw), COUNT(DISTINCT CAST(observed_at AS DATE)) FROM ({base})',
            params).fetchall()[0]
        daily = rows(con, f'''SELECT CAST(observed_at AS DATE) AS date, COUNT(*) AS detections,
                                     SUM(frp_mw) AS sum_frp_mw
                              FROM ({base}) GROUP BY 1 ORDER BY 1''', params)
        for d in daily:
            d['date'], d['detections'] = str(pd.Timestamp(d['date']).date()), int(d['detections'])
        points = as_points(rows(con, f'SELECT * FROM ({base}) ORDER BY hash(id) LIMIT ?', params + [sample]))
        out.append({'sensor': sensor, 'detections': int(n), 'mean_frp_mw': mean_frp,
                    'active_days': int(days), 'daily': daily, 'sample': points})
    return {'region': region, 'month': month, 'sensors': out}


# Bayesian model preview

_preview_store: PreviewStore | None = None


def reset_preview_store():
    global _preview_store
    _preview_store = None


def get_preview_store() -> PreviewStore:
    global _preview_store
    if _preview_store is None:
        d = os.environ.get('PARSEC_PREVIEW_DIR') or Path(__file__).resolve().parents[1] / 'model_preview' / 'bc-july-2023'
        try:
            _preview_store = PreviewStore(d)
        except Exception as exc:
            raise HTTPException(503, 'model preview not available') from exc
    return _preview_store


@app.get('/model-preview/metadata')
def model_preview_metadata(store: PreviewStore = Depends(get_preview_store)):
    return store.metadata


@app.get('/model-preview/cells')
def model_preview_cells(store: PreviewStore = Depends(get_preview_store)):
    return store.geometry


@app.get('/model-preview/validation')
def model_preview_validation(store: PreviewStore = Depends(get_preview_store)):
    return store.validation


@app.get('/model-preview/field')
def model_preview_field(start: str = '2023-07-01', end: str = '2023-07-31',
                        bbox: str = '-139,48,-114,60',
                        limit: int = Query(10000, ge=1, le=10000),
                        offset: int = Query(0, ge=0),
                        store: PreviewStore = Depends(get_preview_store)):
    try:
        return store.field(start, end, bbox, limit, offset)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/model-preview/calendar')
def model_preview_calendar(start: str = '2023-07-01', end: str = '2023-07-31',
                           bbox: str = '-139,48,-114,60',
                           store: PreviewStore = Depends(get_preview_store)):
    try:
        return store.calendar(start, end, bbox)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# B6/B7: the same calendar month across all downloaded years (+ anomaly z-score for B4)

@app.get('/history')
def history(region: str = 'british_columbia', month: int = Query(7, ge=1, le=12, description='1-12'),
            sensor: Literal['MODIS', 'VIIRS', 'harmonized'] = 'MODIS', con=Depends(get_db)):
    """One row per downloaded year for this calendar month: detections, total FRP, fire events
    started, and how unusual the year is against the other years (z-score, percentile, class).
    Only downloaded years appear; missing years are unknown, not zero fires.
    Built from fire_calendar / fire_anomalies (phase2_run --only history --only analytics).
    harmonized has no anomaly yet (anomalies are computed on raw sensors only)."""
    region_bbox(region)
    if sensor == 'harmonized':
        run = latest_run(con)
        where, params = "view = 'harmonized_estimate' AND model_run_id = ?", [run]
    else:
        where, params = "view = 'raw_observed' AND satellite = 'all' AND sensor_family = ?", [sensor]
    try:
        years = rows(con, f'''SELECT year, coverage_state, n_detections, frp_sum_mw, n_fire_events_started
                              FROM fire_calendar WHERE region = ? AND month = ? AND {where}
                              ORDER BY year''', [region, month] + params)
        anomalies = [] if sensor == 'harmonized' else rows(con, '''
            SELECT year, metric, z_score, percentile, anomaly_class, baseline_median, n_baseline_years
            FROM fire_anomalies WHERE region = ? AND month = ? AND sensor_family = ? AND satellite = 'all'
            ''', [region, month, sensor])
    except duckdb.CatalogException:
        raise HTTPException(503, 'no history yet: run phase2_run --only history --only analytics')
    for y in years:
        y['year'] = int(y['year'])
        y['anomaly'] = {a['metric']: {k: a[k] for k in ('z_score', 'percentile', 'anomaly_class',
                                                         'baseline_median', 'n_baseline_years')}
                        for a in anomalies if int(a['year']) == y['year']}
    return {'region': region, 'month': month, 'sensor': sensor, 'years': years}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('phase3.api:app', host='0.0.0.0', port=8000, reload=True)
