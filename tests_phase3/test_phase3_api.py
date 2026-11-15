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
    assert body['status'] == 'unavailable' and body['database_found'] is False


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


# B3 activity matrix

def test_activity_matrix_raw(client):
    modis = client.get('/activity', params={'sensor': 'MODIS'}).json()
    assert len(modis) == 1                                          # test data is July 2023 only
    cell = modis[0]
    assert (cell['year'], cell['month'], cell['detections'], cell['sensor']) == (2023, 7, 101, 'MODIS')
    assert cell['mean_frp_mw'] == pytest.approx(cell['sum_frp_mw'] / 101)
    viirs = client.get('/activity', params={'sensor': 'VIIRS', 'start': '2023-07-01', 'end': '2023-07-03'}).json()
    assert viirs[0]['detections'] == 3 * 61                        # 3 days x (60 matched + 1 lonely)
    assert client.get('/activity', params={'start': '2024-01-01'}).json() == []


def test_activity_matrix_harmonized(harmonized_client):
    cells = harmonized_client.get('/activity', params={'sensor': 'harmonized'}).json()
    assert len(cells) == 1 and cells[0]['detections'] == 100 and cells[0]['sensor'] == 'harmonized'


def test_activity_bad_dates(client):
    assert client.get('/activity', params={'start': '2023-7-1'}).status_code == 422


# B5 comparison

def test_comparison_per_sensor(harmonized_client):
    body = harmonized_client.get('/comparison', params={'month': '2023-07', 'sample': 20}).json()
    by = {s['sensor']: s for s in body['sensors']}
    assert set(by) == {'MODIS', 'VIIRS', 'harmonized'}
    assert (by['MODIS']['detections'], by['VIIRS']['detections'], by['harmonized']['detections']) == (101, 305, 100)
    assert by['VIIRS']['active_days'] == 5 and by['MODIS']['active_days'] == 6     # Terra on 6 July
    assert sum(d['detections'] for d in by['VIIRS']['daily']) == 305
    assert len(by['MODIS']['sample']) == 20
    again = harmonized_client.get('/comparison', params={'month': '2023-07', 'sample': 20}).json()
    assert again == body                                           # same sample every time


def test_comparison_without_model_run(client):
    by = {s['sensor']: s for s in client.get('/comparison').json()['sensors']}
    assert by['harmonized']['detections'] == 0 and 'note' in by['harmonized']


# B6/B7 history

@pytest.fixture
def history_client(phase1_db, cfg, monkeypatch):
    """phase1_db + phase 2 including history and analytics."""
    from phase2.phase2_run import run_pipeline
    run_pipeline(['flags', 'overlap', 'matching', 'events', 'features', 'splits', 'baseline',
                  'history', 'analytics'], start='2023-07-01', end='2023-07-31',
                 db_path=phase1_db, cfg=cfg, plots=False)
    monkeypatch.setenv('PARSEC_DB_PATH', str(phase1_db))
    return TestClient(app)


def test_history_per_year(history_client):
    body = history_client.get('/history?month=7&sensor=MODIS').json()
    assert body['sensor'] == 'MODIS' and [y['year'] for y in body['years']] == [2023]
    y = body['years'][0]
    assert y['n_detections'] == 101
    assert y['coverage_state'] == 'partial_observed' and y['anomaly'] == {}
    harm = history_client.get('/history?month=7&sensor=harmonized').json()['years']
    assert len(harm) == 1 and harm[0]['anomaly'] == {}


def test_history_bad_input_and_no_tables(client):
    assert client.get('/history?month=13').status_code == 422
    assert client.get('/history?region=mars').status_code == 404
    assert client.get('/history?month=7').status_code == 503          # history not built yet


def test_comparison_dates_are_plain(harmonized_client):
    daily = harmonized_client.get('/comparison?month=2023-07&sample=0').json()['sensors'][0]['daily']
    assert daily and len(daily[0]['date']) == 10
