from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from conftest import obs_row
from phase2.phase2_config import load_config
from phase2.phase2_database import load, migrate_table, store, table_counts
from phase2.phase2_fire_events import build_fire_events
from phase2.phase2_overlap import extract_overlap
from phase2.phase2_queries import get_event_detections, get_events, get_overlap


# fire events (2.7)

def test_events_link_space_and_time():
    obs = pd.DataFrame([
        obs_row('A1', 'MODIS', 'Aqua', 53.000, -122.0),
        obs_row('A2', 'VIIRS', 'S-NPP', 53.005, -122.0, minutes=10),   # 0.6 km, same pass
        obs_row('A3', 'VIIRS', 'S-NPP', 53.010, -122.0, day=1),        # next day, 1.1 km
        obs_row('B1', 'VIIRS', 'S-NPP', 55.000, -122.0),               # far away
        obs_row('C1', 'VIIRS', 'S-NPP', 53.000, -122.0, day=3),        # same place, 3 days later
    ])
    events, members = build_fire_events(obs, load_config())
    assert len(events) == 3
    by_obs = members.set_index('observation_id')['event_id']
    assert by_obs['A1'] == by_obs['A2'] == by_obs['A3']
    assert len({by_obs['A1'], by_obs['B1'], by_obs['C1']}) == 3
    big = events.loc[events['n_detections'].idxmax()]
    assert (big['n_modis'], big['n_viirs'], big['sensors']) == (1, 2, 'MODIS,VIIRS')
    assert big['duration_hours'] == pytest.approx(24.0)


def test_every_detection_in_exactly_one_event(phase1_db, cfg):
    obs = extract_overlap(cfg=cfg, db_path=phase1_db, start='2023-07-01')
    events, members = build_fire_events(obs, cfg)
    assert members['observation_id'].is_unique and len(members) == len(obs)
    assert events['n_detections'].sum() == len(obs)


# database + queries (2.15)

def test_store_is_idempotent_and_queries_work(phase1_db, cfg):
    obs = extract_overlap(cfg=cfg, db_path=phase1_db, start='2023-07-01')
    assert store(obs, 'overlap_observations', db_path=phase1_db) == len(obs)
    assert store(obs, 'overlap_observations', db_path=phase1_db) == 0
    assert len(get_overlap(sensor='MODIS', db_path=phase1_db)) == 100
    assert len(load('overlap_observations', db_path=phase1_db, where={'satellite': 'Aqua'})) == 100

    events, members = build_fire_events(obs, cfg)
    store(events, 'fire_events', db_path=phase1_db)
    store(members, 'fire_event_observations', db_path=phase1_db)
    biggest = get_events(db_path=phase1_db).nlargest(1, 'n_detections').iloc[0]
    assert len(get_event_detections(biggest['event_id'], db_path=phase1_db)) == biggest['n_detections']

    counts = table_counts(db_path=phase1_db).set_index('table')['rows']
    assert counts['observations'] == 406         # phase 1 data is untouched


def test_store_rejects_missing_columns(tmp_path):
    with pytest.raises(ValueError, match='missing columns'):
        store(pd.DataFrame({'observation_id': ['x']}), 'overlap_observations',
              db_path=tmp_path / 'db.duckdb')


def test_outdated_table_is_caught_then_migrated(tmp_path):
    db = tmp_path / 'db.duckdb'
    con = duckdb.connect(str(db))
    con.execute('CREATE TABLE model_runs (x INTEGER)')
    con.close()
    with pytest.raises(RuntimeError, match='migrate'):
        load('model_runs', db_path=db)
    migrate_table('model_runs', db_path=db)
    assert load('model_runs', db_path=db).empty