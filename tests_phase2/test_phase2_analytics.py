from __future__ import annotations

import pandas as pd
import pytest

from phase2.phase2_analytics import (anomaly_class, build_anomalies, build_baselines, build_calendar,
                              make_analytics, region_ranking)
from phase2.phase2_history import make_history
from test_phase2_model_interface import prepared_db  # noqa: F401  (fixture)


def july_history(values, states=None, days=31):
    """Fake monthly history: July of 2015, 2016, ... with the given n_detections."""
    rows = []
    for i, v in enumerate(values):
        rows.append(dict(period_start=pd.Timestamp(f'{2015 + i}-07-01'), region='british_columbia',
                         sensor_family='MODIS', satellite='all', days_in_range=days,
                         coverage_state=(states or ['observed'] * len(values))[i],
                         n_detections=v, frp_sum_mw=None if v is None else v * 10.0))
    return pd.DataFrame(rows)


def test_baselines_and_anomalies(cfg):
    cal = build_calendar(july_history([100, 120, 80, 110, 500]), pd.DataFrame(), pd.DataFrame(), cfg)
    base = build_baselines(cal, cfg).set_index('metric')
    assert base.loc['n_detections', 'n_years'] == 5
    assert base.loc['n_detections', 'median'] == 110
    anom = build_anomalies(cal, cfg)
    big = anom[(anom['year'] == 2019) & (anom['metric'] == 'n_detections')].iloc[0]
    assert big['percentile'] == 100 and big['anomaly_class'] == 'much_above_normal'
    assert big['n_baseline_years'] == 4 and big['baseline_median'] == pytest.approx(105)


def test_unknown_and_partial_months_are_left_out(cfg):
    hist = july_history([100, None, 80], states=['observed', 'outage', 'observed'])
    cal = build_calendar(hist, pd.DataFrame(), pd.DataFrame(), cfg)
    assert cal['n_detections'].isna().sum() == 1                 # outage stays unknown, not 0
    assert build_baselines(cal, cfg)['n_years'].max() == 2
    assert set(build_anomalies(cal, cfg)['anomaly_class']) == {'insufficient_history'}
    partial = build_calendar(july_history([100, 90], days=10), pd.DataFrame(), pd.DataFrame(), cfg)
    assert build_baselines(partial, cfg).empty


def test_anomaly_class_and_ranking():
    assert anomaly_class(95, 2) == 'insufficient_history'
    assert anomaly_class(50, 10) == 'normal' and anomaly_class(5, 10) == 'much_below_normal'
    cal = pd.DataFrame({'view': 'raw_observed', 'satellite': 'all', 'year': 2023, 'month': 7,
                        'region': ['a', 'b'], 'sensor_family': 'MODIS', 'frp_sum_mw': [5.0, 9.0]})
    assert list(region_ranking(cal, 2023)['region']) == ['b', 'a']


def test_make_analytics_from_saved_history(prepared_db, cfg):
    from phase2.phase2_model_interface import run_model
    run_id, _ = run_model('identity', 'event', db_path=prepared_db, cfg=cfg)
    make_history(start='2023-07-01', end='2023-07-31', run_id=run_id, db_path=prepared_db, cfg=cfg)
    out = make_analytics(db_path=prepared_db, cfg=cfg)
    cal = out['fire_calendar']
    assert set(cal['view']) == {'raw_observed', 'harmonized_estimate'}
    modis = cal[(cal['view'] == 'raw_observed') & (cal['sensor_family'] == 'MODIS') & (cal['satellite'] == 'all')]
    assert modis['n_detections'].iloc[0] == 101
    assert (out['fire_anomalies']['anomaly_class'] == 'insufficient_history').all()   # one year only