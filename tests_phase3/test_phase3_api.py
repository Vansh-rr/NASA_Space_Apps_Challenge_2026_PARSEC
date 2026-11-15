from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phase3.api import app, get_db, rows


@pytest.fixture
def client(phase1_db, monkeypatch):
    monkeypatch.setenv('PARSEC_DB_PATH', str(phase1_db))
    return TestClient(app)


def test_health_sees_the_database(client):
    r = client.get('/health')
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'ok' and body['database_found'] and body['observations'] == 406


def test_health_without_database(tmp_path, monkeypatch):
    monkeypatch.setenv('PARSEC_DB_PATH', str(tmp_path / 'missing.duckdb'))
    body = TestClient(app).get('/health').json()
    assert body['status'] == 'ok' and body['database_found'] is False


def test_regions(client):
    regions = {r['key']: r for r in client.get('/regions').json()}
    assert regions['british_columbia']['is_default'] is True
    assert regions['british_columbia']['bbox'] == [-139.0, 48.0, -114.0, 60.0]


def test_database_is_read_only(client):
    db = get_db()                       # keep the generator alive while we use the connection
    con = next(db)
    assert rows(con, 'SELECT COUNT(*) AS n FROM observations') == [{'n': 406}]
    with pytest.raises(Exception):
        con.execute('DELETE FROM observations')
    db.close()


def test_cors_allows_the_frontend(client):
    r = client.get('/health', headers={'Origin': 'http://localhost:5173'})
    assert r.headers.get('access-control-allow-origin') in ('*', 'http://localhost:5173')


# B2 observations

@pytest.fixture
def harmonized_client(phase1_db, cfg, monkeypatch):
    """phase1_db + phase 2 up to the identity baseline, so harmonized points exist."""
    from phase2.phase2_run import run_pipeline
    run_pipeline(['flags', 'overlap', 'matching', 'events', 'features', 'splits', 'baseline'],
                 start='2023-07-01', db_path=phase1_db, cfg=cfg, plots=False)
    monkeypatch.setenv('PARSEC_DB_PATH', str(phase1_db))
    return TestClient(app)


def test_observations_raw_sensors(client):
    r = client.get('/observations', params={'month': '2023-07', 'sensor': 'MODIS'})
    assert r.status_code == 200 and r.headers['x-total-count'] == '101'
    first = r.json()[0]
    assert set(first) == {'id', 'latitude', 'longitude', 'frp_mw', 'observed_at', 'sensor', 'is_demo'}
    assert first['sensor'] == 'MODIS' and first['is_demo'] is False
    viirs = client.get('/observations', params={'month': '2023-07', 'sensor': 'VIIRS', 'limit': 10})
    assert len(viirs.json()) == 10 and viirs.headers['x-total-count'] == '305'
    assert client.get('/observations', params={'month': '2023-08'}).json() == []


def test_observations_harmonized(harmonized_client):
    r = harmonized_client.get('/observations', params={'month': '2023-07', 'sensor': 'harmonized'})
    points = r.json()
    assert r.status_code == 200 and len(points) == 100            # one per match group
    assert {p['sensor'] for p in points} == {'harmonized'}
    assert all(40 <= p['frp_mw'] <= 59 for p in points)            # identity = MODIS FRP


def test_observations_bad_input(client):
    assert client.get('/observations', params={'region': 'mars'}).status_code == 404
    assert client.get('/observations', params={'month': 'july'}).status_code == 422
    assert client.get('/observations', params={'sensor': 'GOES'}).status_code == 422