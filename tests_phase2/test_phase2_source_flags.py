from __future__ import annotations

import pandas as pd
import pytest

from conftest import obs_row
from phase1_database import load_standardized
from phase1_modis import standardize_modis
from phase1_viirs import standardize_viirs
from phase2.phase2_source_flags import (flag_observations, flagged_observations, load_registry,
                                 product_versions, save_registry)


def _at(oid, sensor, sat, day, hotspot_type=0):
    row = obs_row(oid, sensor, sat, 53, -122)
    row['acq_datetime_utc'] = pd.Timestamp(day + ' 21:00', tz='UTC')
    row['hotspot_type_raw'] = hotspot_type
    return row


def test_registry_has_the_known_problems():
    reg = load_registry().set_index('flag_id')
    assert str(reg.loc['aqua_fmu_failure_2020', 'start_date']) == '2020-08-16'
    assert str(reg.loc['snpp_safe_mode_2022', 'end_date']) == '2022-08-20'
    assert reg.loc['terra_early_calibration', 'satellite'] == 'Terra'
    assert {'firms_type_1', 'firms_type_2', 'firms_type_3'} <= set(reg.index)


def test_flags_match_satellite_and_dates():
    obs = pd.DataFrame([
        _at('a', 'MODIS', 'Aqua', '2020-08-20'),     # Aqua outage
        _at('b', 'MODIS', 'Aqua', '2020-09-03'),     # day after it ended
        _at('c', 'MODIS', 'Terra', '2020-08-20'),    # Terra was fine then
        _at('d', 'MODIS', 'Terra', '2000-06-01'),    # early Terra data
        _at('e', 'VIIRS', 'S-NPP', '2022-08-01'),    # S-NPP safe mode
        _at('f', 'MODIS', 'Aqua', '2023-07-10', hotspot_type=2),   # industrial hot spot
    ])
    flags = flag_observations(obs).set_index('observation_id')['history_flags']
    assert flags.to_dict() == {'a': 'aqua_fmu_failure_2020', 'b': '', 'c': '',
                               'd': 'terra_early_calibration', 'e': 'snpp_safe_mode_2022',
                               'f': 'firms_type_2'}
    assert len(flag_observations(obs)) == len(obs)          # nothing is deleted


def test_flags_from_the_database(tmp_path):
    db = tmp_path / 'fires.duckdb'
    modis = pd.DataFrame([dict(latitude=53, longitude=-122, brightness=330, bright_t31=295, frp=40,
                               scan=1.2, track=1.1, acq_date=d, acq_time=2100, satellite='A',
                               confidence=80, daynight='D', version='6.1', type=t)
                          for d, t in [('2020-08-20', 0), ('2023-07-10', 2), ('2023-07-11', 0)]])
    viirs = pd.DataFrame([dict(latitude=53, longitude=-122, bright_ti4=340, bright_ti5=295, frp=10,
                               scan=0.4, track=0.4, acq_date='2022-08-01', acq_time=2110,
                               satellite='N', confidence='n', daynight='D', version='2',
                               instrument='VIIRS', type=0)])
    load_standardized(standardize_modis(modis, version='6.1'), 'm', db_path=db, parquet_dir=tmp_path)
    load_standardized(standardize_viirs(viirs, version='2'), 'v', db_path=db, parquet_dir=tmp_path)

    assert save_registry(db_path=db) == 6
    assert save_registry(db_path=db) == 0                   # rerun: no duplicates
    hits = flagged_observations(db_path=db)
    assert sorted(hits['flag_id']) == ['aqua_fmu_failure_2020', 'firms_type_2', 'snpp_safe_mode_2022']
    versions = product_versions(db_path=db)
    assert set(versions['source_dataset']) == {'MODIS_SP', 'VIIRS_SNPP_SP'}


def test_bad_registry_is_rejected(tmp_path):
    bad = tmp_path / 'h.yaml'
    bad.write_text('periods:\n  - {flag_id: x, satellite: Aqua, start: "2021-01-02", end: "2021-01-01", flag: f}\n')
    with pytest.raises(ValueError, match='start is after end'):
        load_registry(bad)