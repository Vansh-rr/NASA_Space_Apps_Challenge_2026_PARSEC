"""Offline ingestion checks using fake inputs and the actual database adapter."""
import pandas as pd
from phase1_database import connect_db, load_standardized
from phase1_modis import standardize_modis
from phase1_viirs import standardize_viirs
from phase1_downloader import split_dates, validate_bbox
import pytest


def raw_modis(**kwargs):
    row = dict(latitude=53, longitude=-122, brightness=330, bright_t31=295,
               frp=20, scan=1.2, track=1.1, acq_date='2023-07-01', acq_time=37,
               satellite='A', confidence=80, daynight='N', version='61.03')
    return pd.DataFrame([row | kwargs])


def test_rerun_is_idempotent_and_raw_is_preserved(tmp_path):
    db = tmp_path/'test.duckdb'
    raw = raw_modis()
    original = raw.copy(deep=True)
    frame = standardize_modis(raw)
    pd.testing.assert_frame_equal(raw, original)
    assert frame.acq_datetime_utc.iloc[0].isoformat() == '2023-07-01T00:37:00+00:00'
    assert load_standardized(frame, 'first', db, tmp_path/'parquet') == 1
    assert load_standardized(frame, 'again', db, tmp_path/'parquet') == 0
    with connect_db(db) as con:
        assert con.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == 1
        assert '"brightness":330' in con.execute('SELECT source_record FROM observations').fetchone()[0]


def test_bad_coordinates_time_and_satellite_are_excluded(tmp_path):
    rows = pd.concat([raw_modis(latitude=100), raw_modis(acq_time=2460),
                      raw_modis(satellite='unknown')], ignore_index=True)
    assert load_standardized(standardize_modis(rows), 'invalid', tmp_path/'bad.duckdb', tmp_path) == 0


def test_viirs_confidence_does_not_become_modis_numeric():
    raw = raw_modis().rename(columns={'brightness':'bright_ti4','bright_t31':'bright_ti5'})
    raw['satellite'], raw['confidence'] = 'N', 'h'
    out = standardize_viirs(raw)
    assert out.confidence_class.iloc[0] == 'high'
    assert out.confidence_numeric.isna().all()


def test_request_bounds_and_date_chunks():
    chunks = split_dates('2023-07-01','2023-07-12')
    assert [((b-a).days+1) for a,b in chunks] == [5,5,2]
    for bbox in [(0,0,float('inf'),10), (170,0,-170,10), (0,10,10,0)]:
        with pytest.raises(ValueError): validate_bbox(bbox)
    with pytest.raises(ValueError): split_dates('2023-07-02','2023-07-01')
