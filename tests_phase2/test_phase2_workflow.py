"""Regression tests for orchestration and source preservation (no database required)."""
from pathlib import Path
from types import SimpleNamespace
from phase2 import workflow


def test_algorithm_sources_unchanged():
    workflow.verify_algorithm()


def test_real_algorithm_uses_absolute_paths_and_separate_outputs(tmp_path):
    args = SimpleNamespace(particles=5000, max_folds=4, nasa_start='2023-07-01',
                           nasa_end='2023-07-08', nasa_bbox=[-139, 48, -114, 60],
                           per_sensor=2, login='interactive', nasa_csv_dir=tmp_path,
                           nasa_raw_dir=None, nasa_live=False, reviewed_data=None)
    assert workflow.algorithm_mode(args) == 'nasa'
    cmd = workflow.algorithm_command('nasa', args, tmp_path / 'reports')
    assert cmd[1] == workflow.ALGORITHM / 'test_parsec_independent.py'
    assert cmd[cmd.index('--csv-dir') + 1] == tmp_path.resolve()
    assert '--full' in cmd
    assert '--live' not in cmd
    assert cmd[cmd.index('--out-root') + 1] == (tmp_path / 'reports').resolve()


def test_unique_runs_and_failed_status(tmp_path):
    a = workflow.fresh(tmp_path)
    b = workflow.fresh(tmp_path)
    assert a != b
    assert workflow.write_status(a, {'engineering': 0, 'algorithm': 2}) == 1
    assert workflow.write_status(b, {'engineering': 0, 'algorithm': 0}) == 0
