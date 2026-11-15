from __future__ import annotations

import numpy as np
import pytest

from phase2.phase2_metrics import compute_metrics
from phase2.phase2_model_interface import register_model, run_model
from phase2.phase2_validation import get_validation, split_method_of, validate
from test_phase2_model_interface import HalfModel, prepared_db  # noqa: F401  (fixture)


def test_metrics_on_known_numbers():
    m = compute_metrics([10, 20, 30], [12, 18, 33], lower=[0, 0, 0], upper=[15, 15, 40])
    assert m['n'] == 3
    assert m['mae'] == pytest.approx(7 / 3)
    assert m['bias'] == pytest.approx(1.0)
    assert m['rmse'] == pytest.approx(np.sqrt(17 / 3))
    assert m['coverage'] == pytest.approx(2 / 3)      # 20 is outside [0, 15]
    perfect = compute_metrics([1, 2, 3], [1, 2, 3])
    assert perfect['mae'] == 0 and perfect['r2'] == 1 and np.isnan(perfect['coverage'])


def test_split_method_of():
    assert split_method_of('2.12.0+cfg2.1.0+event|features:basic') == 'event'


def test_validate_compares_with_baseline(prepared_db, cfg):
    register_model(HalfModel)
    run_id, _ = run_model('test_half', 'event', db_path=prepared_db, cfg=cfg)
    res = validate(run_id, db_path=prepared_db, cfg=cfg, plots=False)
    overall = res[(res['split'] == 'all') & (res['group_by'] == 'all')].set_index('metric')
    # the scaled model must beat "just use MODIS" (MODIS 40-59 MW vs VIIRS 33 MW)
    assert overall.loc['mae', 'value'] < overall.loc['mae', 'baseline_value']
    assert overall.loc['mae', 'skill'] > 0
    assert overall.loc['coverage', 'value'] >= 0
    assert {'modis_satellite', 'daynight', 'n_viirs_bin'} <= set(res['group_by'])
    assert set(res.loc[res['group_by'] == 'n_viirs_bin', 'group_value']) == {'2-5'}   # 3 VIIRS each
    saved = get_validation(run_id, db_path=prepared_db)
    assert len(saved) > 0 and (saved['baseline_run_id'] == res['baseline_run_id'].iloc[0]).all()
    validate(run_id, db_path=prepared_db, cfg=cfg, plots=False)            # rerun: no duplicates
    assert len(get_validation(run_id, db_path=prepared_db)) == len(saved)