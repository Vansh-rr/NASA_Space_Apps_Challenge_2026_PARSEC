from __future__ import annotations

import json

import pytest

from phase2.phase2_database import table_counts
from phase2.phase2_run import STEPS, run_pipeline


def test_full_pipeline_runs_and_reruns_safely(phase1_db, cfg):
    log = run_pipeline(start='2023-07-01', db_path=phase1_db, cfg=cfg, plots=False)
    assert list(log['step']) == STEPS
    result = {r.step: json.loads(r.result) for r in log.itertuples()}
    assert result['matching']['match_groups'] == 100
    assert result['grid']['assignments'] == result['overlap']['detections'] * len(cfg.grid.cell_sizes_km)
    assert result['comparison']['raw_pairs'] == 300
    assert result['features']['feature_rows'] == 100
    assert set(result['datasets']) == set(cfg.splits.names)
    assert result['splits']['leak_free'] is True
    assert result['baseline']['predictions'] == 100

    counts = table_counts(db_path=phase1_db).set_index('table')['rows']
    assert counts['observations'] == 406                  # phase 1 untouched
    run_pipeline(start='2023-07-01', db_path=phase1_db, cfg=cfg, plots=False)
    assert table_counts(db_path=phase1_db).set_index('table')['rows'].equals(counts)   # no duplicates


def test_steps_run_in_order_and_can_start_in_the_middle(phase1_db, cfg):
    run_pipeline(['overlap', 'flags'], start='2023-07-01', db_path=phase1_db, cfg=cfg)
    log = run_pipeline(['splits', 'matching', 'events'], db_path=phase1_db, cfg=cfg)
    assert list(log['step']) == ['matching', 'events', 'splits']


def test_dashboard_steps_fill_their_tables(phase1_db, cfg):
    run_pipeline(start='2023-07-01', end='2023-07-31', db_path=phase1_db, cfg=cfg, plots=False)
    counts = table_counts(db_path=phase1_db).set_index('table')['rows']
    for table in ['sensor_comparison_summary', 'historical_observations',
                  'historical_harmonized_activity', 'fire_calendar', 'seasonal_baselines']:
        assert counts[table] > 0, table


def test_unknown_step():
    with pytest.raises(ValueError, match='unknown steps'):
        run_pipeline(['nope'])