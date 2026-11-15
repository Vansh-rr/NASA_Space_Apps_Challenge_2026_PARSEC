from __future__ import annotations

from fastapi.testclient import TestClient

from phase3.api import app, reset_preview_store

client = TestClient(app)


def test_model_preview_metadata():
    r = client.get('/model-preview/metadata')
    assert r.status_code == 200
    body = r.json()
    assert body['cells'] == 10 and body['rows'] == 1280


def test_model_preview_field():
    r = client.get('/model-preview/field')
    assert r.status_code == 200
    assert r.json()['total'] == 1280
    r2 = client.get('/model-preview/field', params={'limit': 2})
    items = r2.json()['items']
    assert len(items) == 2
    assert all('p_fire' in item and 'cell_id' in item for item in items)


def test_model_preview_calendar():
    r = client.get('/model-preview/calendar')
    assert r.status_code == 200
    items = r.json()['items']
    assert len(items) == 31
    by_date = {item['date']: item for item in items}
    assert by_date['2023-07-01']['coverage_status'] == 'observed'


def test_model_preview_cells():
    r = client.get('/model-preview/cells')
    assert r.status_code == 200
    body = r.json()
    assert body['type'] == 'FeatureCollection' and isinstance(body['features'], list)


def test_model_preview_validation():
    r = client.get('/model-preview/validation')
    assert r.status_code == 200
    assert 'comparison' in r.json()


def test_model_preview_bad_bbox():
    r = client.get('/model-preview/field', params={'bbox': '1,2'})
    assert r.status_code == 422


def test_model_preview_missing_dir(tmp_path, monkeypatch):
    reset_preview_store()
    try:
        monkeypatch.setenv('PARSEC_PREVIEW_DIR', str(tmp_path / 'missing'))
        r = client.get('/model-preview/metadata')
        assert r.status_code == 503
        assert r.json()['detail'] == 'model preview not available'
    finally:
        reset_preview_store()
