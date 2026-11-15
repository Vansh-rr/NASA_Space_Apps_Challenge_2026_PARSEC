"""Check the runner's failure reporting without invoking its own suite recursively."""
import json
import run_tests


def test_preflight_failure_is_nonzero_and_reported(tmp_path,monkeypatch):
    monkeypatch.setattr(run_tests,'ROOT',tmp_path)
    monkeypatch.setattr(run_tests,'preflight',lambda *a:['Missing required compiler'])
    assert run_tests.main(['--skip-frontend','--skip-algorithm']) == 1
    report=json.loads(next((tmp_path/'test-results').glob('*/summary.json')).read_text())
    assert report['passed'] is False
    assert report['full_suite'] is False
    assert report['preflight_errors'] == ['Missing required compiler']


def test_failed_stage_preserves_nonzero_code_and_log(tmp_path):
    import sys,os
    run_tests_root=run_tests.ROOT
    # stage logs normally live below ROOT; use a temporary directory below it.
    import tempfile
    with tempfile.TemporaryDirectory(dir=run_tests_root) as d:
        from pathlib import Path
        result=run_tests.stage('intentional_failure',[sys.executable,'-c',"print('sentinel'); raise SystemExit(7)"],
                               run_tests_root,os.environ.copy(),Path(d),10)
        assert result['passed'] is False and result['exit_code'] == 7
        assert 'sentinel' in (run_tests_root/result['log']).read_text()
