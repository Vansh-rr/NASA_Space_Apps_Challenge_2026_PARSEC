from __future__ import annotations

import duckdb
import pydantic
import pytest

from phase2.phase2_config import load_config
from phase2.phase2_schema import (TABLES, columns_of, create_table_sql, match_group_id,
                           model_run_id, stable_id)


def test_config_loads(cfg):
    assert cfg.default_region in cfg.regions
    assert cfg.matching.max_time_diff_minutes > 0
    assert cfg.version('matching').startswith(cfg.dataset_versions['matching'])


def test_config_rejects_unknown_region():
    with pytest.raises(pydantic.ValidationError, match='default_region'):
        load_config(default_region='nope')


def test_config_rejects_bad_bbox():
    with pytest.raises(pydantic.ValidationError, match='bbox'):
        load_config(regions={'x': {'name': 'x', 'bbox': [10, 0, 5, 1]}}, default_region='x')


def test_demo_output_is_separate():
    real = load_config().output_dir('t')
    demo = load_config(demo_mode=True).output_dir('t')
    assert real != demo and 'demo' in demo.parts


def test_every_table_creates():
    con = duckdb.connect()
    for name in TABLES:
        con.execute(create_table_sql(name))
        cols, key = TABLES[name]
        assert set(key) <= set(cols)
        assert [r[1] for r in con.execute(f"PRAGMA table_info('{name}')").fetchall()] == columns_of(name)


def test_ids_are_stable():
    assert match_group_id('a', '1') == match_group_id('a', '1')
    assert match_group_id('a', '1') != match_group_id('a', '2')
    assert stable_id('x', 1, 'b').startswith('x_')
    assert model_run_id('m', '1', 'd', {'b': 1, 'a': 2}) == model_run_id('m', '1', 'd', {'a': 2, 'b': 1})