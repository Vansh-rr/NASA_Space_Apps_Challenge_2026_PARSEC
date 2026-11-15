from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase2.phase2_database import store
from phase2.phase2_fire_events import build_fire_events
from phase2.phase2_matching import run_matching
from phase2.phase2_model_interface import (HarmonizationModel, IdentityModel, get_model, list_runs,
                                    load_predictions, register_model, run_model)
from phase2.phase2_overlap import extract_overlap
from phase2.phase2_prediction_schema import check_model_output


@pytest.fixture
def prepared_db(phase1_db, cfg):
    """phase1_db + matching + fire events stored, so models can run."""
    obs = extract_overlap(cfg=cfg, db_path=phase1_db, start='2023-07-01')
    store(run_matching(obs, cfg).matched, 'matched_observations', db_path=phase1_db)
    events, members = build_fire_events(obs, cfg)
    store(events, 'fire_events', db_path=phase1_db)
    store(members, 'fire_event_observations', db_path=phase1_db)
    return phase1_db


class HalfModel(HarmonizationModel):
    """Test-only model: learns one scale factor, gives a +-10% interval."""
    name, version = 'test_half', '0.1'

    def fit(self, train):
        self.k = float(train['reference_value'].sum() / train['source_value'].sum())
        return self

    def predict(self, data):
        p = data['source_value'] * self.k
        return pd.DataFrame({'unit_id': data['unit_id'], 'predicted_value': p,
                             'predicted_lower': p * 0.9, 'predicted_upper': p * 1.1})

    def parameters(self):
        return {'k': round(self.k, 6)}


def test_identity_baseline_runs_and_saves(prepared_db, cfg):
    run_id, pred = run_model('identity', 'event', db_path=prepared_db, cfg=cfg)
    assert len(pred) == 100
    assert (pred['predicted_value'] == pred['source_value']).all()
    assert set(pred['split']) <= {'train', 'validation', 'test'}
    again, _ = run_model('identity', 'event', db_path=prepared_db, cfg=cfg)
    assert again == run_id and len(list_runs(db_path=prepared_db)) == 1   # same run, no duplicate
    assert len(load_predictions(run_id, db_path=prepared_db)) == 100


def test_custom_model_plugs_in(prepared_db, cfg):
    register_model(HalfModel)
    run_id, pred = run_model('test_half', 'event', db_path=prepared_db, cfg=cfg)
    assert pred['predicted_lower'].notna().all()
    # source values are 40-59 MW, references 33 MW: the learned factor is below 1
    assert (pred['predicted_value'] < pred['source_value']).all()
    runs = list_runs(db_path=prepared_db).set_index('model_run_id')
    assert runs.loc[run_id, 'model_name'] == 'test_half' and '"k"' in runs.loc[run_id, 'parameters']


def test_models_never_see_the_answer(prepared_db, cfg):
    class Peek(IdentityModel):
        name = 'test_peek'
        def predict(self, data):
            assert not {'reference_value', 'viirs_frp_sum_mw', 'viirs_frp_max_mw',
                        'log_frp_viirs_sum'} & set(data.columns)
            return super().predict(data)
    run_model(Peek(), 'event', db_path=prepared_db, cfg=cfg, save=False)


def test_bad_model_output_is_caught():
    inp = pd.DataFrame({'unit_id': ['a', 'b'], 'source_value': [1.0, 2.0]})
    with pytest.raises(ValueError, match='missing columns'):
        check_model_output(pd.DataFrame({'unit_id': ['a', 'b']}), inp)
    with pytest.raises(ValueError, match='do not match'):
        check_model_output(pd.DataFrame({'unit_id': ['a'], 'predicted_value': [1.0]}), inp)
    with pytest.raises(ValueError, match='infinite'):
        check_model_output(pd.DataFrame({'unit_id': ['a', 'b'], 'predicted_value': [1.0, np.inf]}), inp)
    with pytest.raises(ValueError, match='outside'):
        check_model_output(pd.DataFrame({'unit_id': ['a', 'b'], 'predicted_value': [1.0, 5.0],
                                         'predicted_lower': [0.5, 1.0], 'predicted_upper': [2.0, 3.0]}), inp)


def test_unknown_model_name():
    with pytest.raises(ValueError, match='unknown model'):
        get_model('nope')
        