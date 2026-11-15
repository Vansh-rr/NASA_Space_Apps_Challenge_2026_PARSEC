from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase2.phase2_database import load, store
from phase2.phase2_matching import run_matching
from phase2.phase2_overlap import extract_overlap, store_overlap_table
from phase2.phase2_sensor_comparison import (_confidence_label, aggregate_groups, build_comparison_pairs,
                                      compute_comparison_stats, group_view, make_comparison)


@pytest.fixture
def compared_db(phase1_db, cfg):
    obs = extract_overlap(cfg=cfg, db_path=phase1_db, start='2023-07-01')
    store_overlap_table(obs, db_path=phase1_db)
    r = run_matching(obs, cfg)
    store(r.matched, 'matched_observations', db_path=phase1_db)
    store(r.unmatched, 'unmatched_observations', db_path=phase1_db)
    return phase1_db


def test_confidence_mixes_numbers_and_words():
    out = _confidence_label(pd.Series([80, None]), pd.Series([None, 'nominal']))
    assert list(out) == [80, 'nominal']


def test_groups_compare_against_summed_viirs(compared_db, cfg):
    from phase2.phase2_sensor_comparison import load_inputs
    obs, matched, _ = load_inputs(cfg.default_region, compared_db, cfg=cfg)
    pairs = build_comparison_pairs(matched, obs)
    groups = aggregate_groups(pairs)
    assert len(pairs) == 300 and len(groups) == 100
    # test data: MODIS 40-59 MW, each with 3 VIIRS of 10, 11, 12 MW
    assert (groups['viirs_frp_sum_mw'] == 33).all() and (groups['n_viirs'] == 3).all()
    per_pair = compute_comparison_stats(pairs, by=()).iloc[0]
    per_group = compute_comparison_stats(group_view(groups), by=()).iloc[0]
    assert per_pair['frp_ratio_median'] < 0.3 < per_group['frp_ratio_median']   # one pixel vs the sum


def test_make_comparison_saves_summary(compared_db, cfg):
    s = make_comparison(db_path=compared_db, cfg=cfg, plots=False)
    assert {'detections', 'matching', 'pairs', 'groups'} <= set(s['section'])
    m = s[(s['section'] == 'matching') & (s['group_value'] == 'S-NPP')].set_index('metric')['value']
    assert m['n_detections'] == 305 and m['n_matched'] == 300
    saved = load('sensor_comparison_summary', db_path=compared_db)
    assert len(saved) == len(s)
    make_comparison(db_path=compared_db, cfg=cfg, plots=False)                 # rerun: no duplicates
    assert len(load('sensor_comparison_summary', db_path=compared_db)) == len(s)


# Vansh's independent check (kept)
def test_raw_comparison_and_group_frp():
    matched = pd.DataFrame([dict(match_group_id='m', region='r', modis_observation_id='M',
        viirs_observation_id=v, modis_satellite='Aqua', viirs_satellite='S-NPP', daynight='D',
        distance_km=.3, time_diff_minutes=10, n_viirs_in_group=2, dataset_version='fixture')
        for v in ['V1', 'V2']])
    observations = pd.DataFrame([dict(observation_id=i, frp_mw=f, acq_date='2023-07-01',
            confidence_numeric=c, confidence_class=k) for i, f, c, k in
            [('M', 40., 80, None), ('V1', 10., None, 'nominal'), ('V2', 20., None, 'high')]])
    pairs = build_comparison_pairs(matched, observations)
    assert len(pairs) == 2
    assert np.allclose(pairs.log_frp_ratio, np.log([.25, .5]))
    groups = aggregate_groups(pairs)
    assert groups.viirs_frp_sum_mw.iloc[0] == 30
    assert groups.modis_frp_mw.iloc[0] == 40
    assert compute_comparison_stats(pairs).n_pairs.iloc[0] == 2