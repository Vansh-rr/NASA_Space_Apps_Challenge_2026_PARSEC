"""Create the existing test fixture in an isolated demo database, never real data."""
from phase1_database import DEMO_DB_PATH
from phase1_storage import DATA_DIR

def seed_demo():
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

    db = DEMO_DB_PATH
    load_standardized(standardize_modis(pd.DataFrame(modis), version='6.1'), 'test_modis',
                      db_path=db, parquet_dir=DATA_DIR / 'demo' / 'standardized')
    load_standardized(standardize_viirs(pd.DataFrame(viirs), version='2'), 'test_viirs',
                      db_path=db, parquet_dir=DATA_DIR / 'demo' / 'standardized')
    return db

if __name__ == "__main__":
    print("Synthetic Phase 2 fixture:", seed_demo())

