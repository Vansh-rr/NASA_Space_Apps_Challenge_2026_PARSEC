import duckdb
from fastapi.testclient import TestClient
from phase3.api import app
from test_phase3_api import client, harmonized_client


def test_pagination_is_complete_and_stable(client):
    a = client.get('/observations?sensor=MODIS&limit=50&offset=0')
    b = client.get('/observations?sensor=MODIS&limit=50&offset=50')
    c = client.get('/observations?sensor=MODIS&limit=50&offset=100')
    all_rows = a.json()+b.json()+c.json()
    assert a.headers['x-total-count'] == '101'
    assert len({r['id'] for r in all_rows}) == 101
    assert client.get('/observations?offset=-1').status_code == 422


def test_invalid_calendar_dates_are_client_errors(client):
    for url in ['/activity?start=2023-02-30', '/activity?start=2023-08-01&end=2023-07-01',
                '/observations?month=0000-01', '/comparison?month=0000-07']:
        assert client.get(url).status_code == 422, url


def test_health_and_queries_handle_invalid_database(tmp_path,monkeypatch):
    path=tmp_path/'incompatible.duckdb'
    with duckdb.connect(str(path)) as con: con.execute('CREATE TABLE something_else(i INT)')
    monkeypatch.setenv('PARSEC_DB_PATH',str(path))
    c=TestClient(app)
    assert c.get('/health').status_code == 503
    assert c.get('/health').json()['status'] == 'unavailable'
    assert c.get('/observations').status_code == 503


def test_harmonized_does_not_expose_a_synthetic_run_in_real_mode(harmonized_client,phase1_db):
    with duckdb.connect(str(phase1_db)) as con:
        con.execute('UPDATE model_runs SET is_synthetic = true')
    assert harmonized_client.get('/observations?sensor=harmonized').json() == []


def test_demo_flag_survives_empty_comparison(client,monkeypatch):
    monkeypatch.setenv('PARSEC_DEMO','1')
    assert client.get('/comparison?month=2023-08').json()['is_demo'] is True


def test_activity_propagates_demo_provenance(client,monkeypatch):
    monkeypatch.setenv('PARSEC_DEMO','1')
    data=client.get('/activity?sensor=MODIS').json()
    assert data and all(r['is_demo'] is True for r in data)
