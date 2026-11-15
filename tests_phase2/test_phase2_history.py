from __future__ import annotations

import pandas as pd

from conftest import obs_row
from phase2.phase2_history import build_history, get_history, make_history, period_start
from phase2.phase2_model_interface import run_model
from test_phase2_model_interface import prepared_db  # noqa: F401  (fixture)


def test_period_start():
    d = ['2023-01-01', '2023-01-09', '2023-07-15', '2023-12-31']
    assert list(period_start(d, '8day').dt.strftime('%m-%d')) == ['01-01', '01-09', '07-12', '12-27']
    assert list(period_start(d, 'month').dt.strftime('%m-%d')) == ['01-01', '01-01', '07-01', '12-01']


def test_missing_is_not_zero(cfg):
    obs = pd.DataFrame([obs_row('a', 'MODIS', 'Aqua', 53, -122, frp=20),
                        obs_row('b', 'MODIS', 'Aqua', 53, -122, frp=40, day=1)])
    obs['is_flagged'] = False
    # aqua fmu failure 16 aug - 2 sep 2020; S-NPP not launched in 2011
    h = build_history(obs, 'day', 'british_columbia', '2023-07-10', '2023-07-12', cfg)
    aqua = h[h['satellite'] == 'Aqua'].set_index('period_start')
    assert list(aqua['coverage_state']) == ['partial_observed', 'partial_observed', 'unknown']
    assert list(aqua['n_detections'].iloc[:2]) == [1, 1]
    assert pd.isna(aqua['n_detections'].iloc[2])
    assert aqua['frp_sum_mw'].iloc[0] == 20

    out = build_history(obs.iloc[:0], 'day', 'british_columbia', '2020-08-20', '2020-08-20', cfg)
    states = out.set_index('satellite')['coverage_state']
    assert states['Aqua'] == 'outage' and states['Terra'] == 'unknown'
    assert out.set_index('satellite').loc['Aqua', 'n_detections'] is pd.NA
    early = build_history(obs.iloc[:0], 'day', 'british_columbia', '2011-05-01', '2011-05-01', cfg)
    assert early.set_index('satellite').loc['S-NPP', 'coverage_state'] == 'sensor_unavailable'


def test_make_history_saves_and_adds_harmonized(prepared_db, cfg):
    run_id, _ = run_model('identity', 'event', db_path=prepared_db, cfg=cfg)
    h = make_history(start='2023-07-01', end='2023-07-07', run_id=run_id, db_path=prepared_db, cfg=cfg)
    day = get_history('day', sensor_family='MODIS', db_path=prepared_db, cfg=cfg)
    assert len(day) == 7 and day['n_detections'].sum() == 101          # 100 Aqua + 1 Terra
    assert (h['month']['days_in_range'] == 7).all()
    make_history(start='2023-07-01', end='2023-07-07', db_path=prepared_db, cfg=cfg)   # rerun
    assert len(get_history('day', sensor_family='MODIS', db_path=prepared_db, cfg=cfg)) == 7
