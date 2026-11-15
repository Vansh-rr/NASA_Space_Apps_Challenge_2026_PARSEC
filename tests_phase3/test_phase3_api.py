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