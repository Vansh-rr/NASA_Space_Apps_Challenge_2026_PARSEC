from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

# tests never touch the real data/ folder: point PARSEC_DATA_DIR to a temp folder
# (must happen before any phase1/phase2 module is imported)
os.environ['PARSEC_DATA_DIR'] = tempfile.mkdtemp(prefix='parsec_tests_')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

T0 = pd.Timestamp('2023-07-10 21:00', tz='UTC')


def obs_row(oid, sensor, satellite, lat, lon, minutes=0, frp=10.0, area=None,
            region='british_columbia', daynight='D', day=0):
    """One overlap_observations-style row for small hand-made test cases."""
    area = area if area is not None else (1.0 if sensor == 'MODIS' else 0.14)
    return dict(observation_id=oid, region=region, sensor_family=sensor, satellite=satellite,
                source_dataset='MODIS_SP' if sensor == 'MODIS' else 'VIIRS_SNPP_SP',
                acq_datetime_utc=T0 + pd.Timedelta(days=day, minutes=minutes),
                daynight=daynight, latitude=lat, longitude=lon, frp_mw=frp,
                scan_km=area ** 0.5, track_km=area ** 0.5, pixel_area_km2=area,
                dataset_version='test')


@pytest.fixture
def cfg():
    from phase2.phase2_config import load_config
    return load_config()


@pytest.fixture
def phase1_db(tmp_path):
    """Small phase 1 DuckDB built from fake FIRMS rows through the real phase 1 code.

    5 days x 20 Aqua MODIS fires, each with 3 S-NPP VIIRS pixels ~0.3 km away 10 min later,
    1 lonely VIIRS far away per day, and 1 Terra MODIS on a day without any VIIRS.
    """
    import numpy as np
    from phase1_database import load_standardized
    from phase1_modis import standardize_modis
    from phase1_viirs import standardize_viirs

    rng = np.random.default_rng(0)
    modis, viirs = [], []
    for day in range(1, 6):
        d = f'2023-07-{day:02d}'
        for i in range(20):
            lat, lon = 53 + rng.uniform(-1, 1), -122 + rng.uniform(-1, 1)
            modis.append(dict(latitude=lat, longitude=lon, brightness=330, bright_t31=295,
                              frp=40 + i, scan=1.2, track=1.1, acq_date=d, acq_time=2100,
                              satellite='A', confidence=80, daynight='D', version='6.1'))
            for k in range(3):
                viirs.append(dict(latitude=lat + 0.002 * k, longitude=lon + 0.003,
                                  bright_ti4=340, bright_ti5=295, frp=10 + k, scan=0.4,
                                  track=0.4, acq_date=d, acq_time=2110, satellite='N',
                                  confidence='n', daynight='D', version='2',
                                  instrument='VIIRS'))
        viirs.append(dict(latitude=58, longitude=-130, bright_ti4=340, bright_ti5=295, frp=5,
                          scan=0.4, track=0.4, acq_date=d, acq_time=2110, satellite='N',
                          confidence='l', daynight='D', version='2', instrument='VIIRS'))
    modis.append(dict(latitude=53, longitude=-122, brightness=330, bright_t31=295, frp=40,
                      scan=1.2, track=1.1, acq_date='2023-07-06', acq_time=1900,
                      satellite='T', confidence=80, daynight='D', version='6.1'))

    db = tmp_path / 'fires.duckdb'
    load_standardized(standardize_modis(pd.DataFrame(modis), version='6.1'), 'test_modis',
                      db_path=db, parquet_dir=tmp_path / 'std')
    load_standardized(standardize_viirs(pd.DataFrame(viirs), version='2'), 'test_viirs',
                      db_path=db, parquet_dir=tmp_path / 'std')
    return db


def pytest_configure(config):
    # warning from inside the duckdb library (not our code), hide it in test output
    config.addinivalue_line('filterwarnings', 'ignore:The inplace keyword in DataFrame.drop')