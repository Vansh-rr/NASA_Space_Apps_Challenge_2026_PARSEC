from __future__ import annotations

import pandas as pd
import pytest

from conftest import obs_row
from phase2.phase2_config import load_config
from phase2.phase2_matching import run_matching
from phase2.phase2_overlap import extract_overlap
from phase2.phase2_spatial_matching import build_match_candidates, find_unmatched, haversine_km
from phase2.phase2_temporal import (add_time_window_ids, assign_overpasses, build_overpass_groups,
                             build_overpass_pairs)


# overlap (2.2)

def test_overlap_keeps_only_days_with_both_sensors(phase1_db, cfg):
    df = extract_overlap(cfg=cfg, db_path=phase1_db, start='2023-07-01', end='2023-07-31')
    assert len(df) == 405                       # the Terra-only day is dropped
    assert set(df['region']) == {'british_columbia'}
    assert 'Terra' not in set(df['satellite'])


def test_overlap_rejects_dates_before_overlap(phase1_db, cfg):
    with pytest.raises(ValueError, match='overlap period'):
        extract_overlap(cfg=cfg, db_path=phase1_db, start='2010-01-01', end='2011-01-01')


# temporal (2.4)

def test_overpasses_and_pairs():
    obs = pd.DataFrame([
        obs_row('M1', 'MODIS', 'Aqua', 53, -122, minutes=0),
        obs_row('M2', 'MODIS', 'Aqua', 53, -122, minutes=2),      # same pass as M1
        obs_row('M3', 'MODIS', 'Aqua', 53, -122, minutes=120),    # next pass
        obs_row('V1', 'VIIRS', 'S-NPP', 53, -122, minutes=10),
    ])
    cfg = load_config()
    a = assign_overpasses(obs, cfg)
    ids = a.set_index('observation_id')['overpass_id']
    assert ids['M1'] == ids['M2'] != ids['M3']
    ovp = build_overpass_groups(a, cfg)
    assert sorted(ovp['n_detections']) == [1, 1, 2]
    pairs = build_overpass_pairs(ovp, cfg)
    assert len(pairs) == 1                       # only the first Aqua pass is within 30 min


def test_time_windows():
    out = add_time_window_ids(pd.DataFrame({'acq_date': ['2023-01-09', '2024-12-31']}))
    assert [str(d) for d in out['window_8day']] == ['2023-01-09', '2024-12-26']
    assert [str(d) for d in out['window_month']] == ['2023-01-01', '2024-12-01']


# spatial (2.5)

def test_haversine_one_degree_latitude():
    assert haversine_km(0, 0, 1, 0) == pytest.approx(111.19, abs=0.1)


def test_candidates_and_unmatched_reasons():
    obs = pd.DataFrame([
        obs_row('M1', 'MODIS', 'Aqua', 53.0, -122.0),
        obs_row('V1', 'VIIRS', 'S-NPP', 53.003, -122.0, minutes=10),   # ~0.3 km: match
        obs_row('V2', 'VIIRS', 'S-NPP', 54.0, -122.0, minutes=10),     # ~111 km: too far
        obs_row('V3', 'VIIRS', 'S-NPP', 53.0, -122.0, minutes=300),    # 5 h later: other pass
    ])
    cfg = load_config()
    a = assign_overpasses(obs, cfg)
    pairs = build_overpass_pairs(build_overpass_groups(a, cfg), cfg)
    cand = build_match_candidates(a, pairs, cfg)
    assert list(cand['viirs_observation_id']) == ['V1']
    reasons = find_unmatched(a, pairs, cand, cfg).set_index('observation_id')['reason']
    assert reasons['V2'] == 'no_candidate_in_space'
    assert reasons['V3'] == 'no_candidate_in_time'


# combined matching (2.6)

def _two_overlapping_modis():
    rows = [obs_row('M1', 'MODIS', 'Aqua', 53.000, -122.0),
            obs_row('M2', 'MODIS', 'Aqua', 53.009, -122.0)]      # 1 km apart
    rows += [obs_row(f'V{k}', 'VIIRS', 'S-NPP', 53.000 + 0.0018 * k, -122.0, minutes=10)
             for k in range(6)]                                   # all reachable from both
    return pd.DataFrame(rows)


def test_each_viirs_in_one_group_only():
    m = run_matching(_two_overlapping_modis(), load_config()).matched
    assert m['viirs_observation_id'].is_unique
    groups = m.groupby('modis_observation_id')['viirs_observation_id'].apply(set).to_dict()
    assert groups == {'M1': {'V0', 'V1', 'V2'}, 'M2': {'V3', 'V4', 'V5'}}   # closest MODIS wins


def test_every_detection_accounted_once():
    obs = _two_overlapping_modis()
    obs = pd.concat([obs, pd.DataFrame([obs_row('M3', 'MODIS', 'Aqua', 53.004, -122.0)])])
    r = run_matching(obs, load_config())
    matched = set(r.matched['modis_observation_id']) | set(r.matched['viirs_observation_id'])
    unmatched = set(r.unmatched['observation_id'])
    assert matched | unmatched == set(obs['observation_id'])
    assert not matched & unmatched


def test_group_cap():
    cfg = load_config()
    cfg = load_config(matching={**cfg.matching.model_dump(), 'max_viirs_per_modis': 3})
    obs = pd.DataFrame([obs_row('M', 'MODIS', 'Aqua', 54.0, -121.0)] +
                       [obs_row(f'W{k}', 'VIIRS', 'S-NPP', 54.0 + 0.001 * k, -121.0, minutes=10)
                        for k in range(5)])
    r = run_matching(obs, cfg)
    assert sorted(r.matched['viirs_observation_id']) == ['W0', 'W1', 'W2']
    assert set(r.unmatched.loc[r.unmatched['reason'] == 'over_group_cap', 'observation_id']) == {'W3', 'W4'}


def test_matching_on_phase1_data(phase1_db, cfg):
    r = run_matching(extract_overlap(cfg=cfg, db_path=phase1_db, start='2023-07-01'), cfg)
    assert r.summary['match_groups'] == 100 and r.summary['matched_viirs'] == 300
    assert r.matched['viirs_observation_id'].is_unique