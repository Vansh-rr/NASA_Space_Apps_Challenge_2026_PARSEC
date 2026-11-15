from __future__ import annotations

import numpy as np
import pandas as pd
import pydantic
import pytest

from phase2.phase2_config import load_config
from phase2.phase2_database import store
from phase2.phase2_dataset_builder import build_model_input, load_split
from phase2.phase2_fire_events import build_fire_events
from phase2.phase2_matching import run_matching
from phase2.phase2_overlap import extract_overlap
from phase2.phase2_schema import MODEL_INPUT_REQUIRED
from phase2.phase2_splits import check_no_leak, make_splits, split_units


def _units(n_events=40, per_event=5):
    rng = np.random.default_rng(1)
    rows = []
    for e in range(n_events):
        lat, lon, day = 50 + rng.uniform(0, 9), -135 + rng.uniform(0, 20), int(rng.integers(0, 30))
        for k in range(per_event):
            rows.append(dict(unit_id=f'u{e}_{k}', event_id=f'e{e}',
                             time=pd.Timestamp('2023-07-01', tz='UTC') + pd.Timedelta(days=day, hours=k),
                             latitude=lat + 0.001 * k, longitude=lon))
    return pd.DataFrame(rows)


@pytest.mark.parametrize('method', ['event', 'time', 'region'])
def test_no_fire_in_two_splits(method):
    units = _units()
    s = split_units(units, method, load_config())
    assert check_no_leak(s)
    per_event = s.merge(units, on='unit_id').groupby('event_id')['split'].nunique()
    assert (per_event == 1).all()
    shares = s['split'].value_counts(normalize=True)
    assert shares['train'] == pytest.approx(0.7, abs=0.1)


def test_splits_are_reproducible():
    units = _units()
    cfg = load_config()
    a = split_units(units, 'event', cfg)
    b = split_units(units.sample(frac=1, random_state=3), 'event', cfg)
    assert a.set_index('unit_id')['split'].sort_index().equals(b.set_index('unit_id')['split'].sort_index())
    other = load_config(splits={**cfg.splits.model_dump(), 'seed': 7})
    assert not a['split'].equals(split_units(units, 'event', other)['split'])


def test_time_split_puts_older_fires_in_train():
    units = _units()
    s = split_units(units, 'time', load_config()).merge(units, on='unit_id')
    starts = s.groupby(['split', 'event_id'])['time'].min().groupby('split')
    assert starts.max()['train'] <= starts.min()['test']


def test_unknown_method_and_bad_fractions():
    with pytest.raises(ValueError, match='unknown split method'):
        split_units(_units(), 'nope', load_config())
    cfg = load_config()
    with pytest.raises(pydantic.ValidationError, match='add up to 1'):
        load_config(splits={**cfg.splits.model_dump(), 'fractions': [0.5, 0.2, 0.2]})


def test_model_input_end_to_end(phase1_db, cfg):
    obs = extract_overlap(cfg=cfg, db_path=phase1_db, start='2023-07-01')
    store(run_matching(obs, cfg).matched, 'matched_observations', db_path=phase1_db)
    events, members = build_fire_events(obs, cfg)
    store(events, 'fire_events', db_path=phase1_db)
    store(members, 'fire_event_observations', db_path=phase1_db)

    splits = make_splits('event', db_path=phase1_db, cfg=cfg)
    assert len(splits) == 100 and check_no_leak(splits)
    assert store(splits, 'dataset_splits', db_path=phase1_db) == 0      # already saved

    data = build_model_input('event', db_path=phase1_db, cfg=cfg)
    assert set(MODEL_INPUT_REQUIRED) <= set(data.columns) and len(data) == 100
    assert (data['n_viirs'] == 3).all()                                # 3 VIIRS per MODIS fire
    assert data['reference_value'].iloc[0] == pytest.approx(33.0)      # 10 + 11 + 12 MW
    train = load_split('train', 'event', db_path=phase1_db, cfg=cfg)
    assert 0 < len(train) < 100 and set(train['split']) == {'train'}