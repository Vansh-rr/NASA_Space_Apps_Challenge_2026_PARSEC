#!/usr/bin/env python3
"""Run all offline checks: python run_tests.py [--install]. No NASA credentials needed."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / 'firesync-app'
PYTEST_TARGETS = ['tests_phase1', 'tests_phase2', 'tests_phase3', 'tests_tools', 'test_model_preview.py']
REQUIRED = ['pytest', 'pandas', 'numpy', 'duckdb', 'pyarrow', 'pyproj', 'shapely',
            'geopandas', 'fastapi', 'httpx', 'netCDF4', 'h5py', 'yaml', 'scipy']


def preflight(frontend=True, algorithm=True):
    problems = []
    if sys.version_info < (3, 11):
        problems.append('Python 3.11 or newer is required (tested with 3.12).')
    missing = [name for name in REQUIRED if importlib.util.find_spec(name) is None]
    if missing:
        problems.append('Missing Python modules: '+', '.join(missing)+'. Run python run_tests.py --install.')
    if not shutil.which('gcc'):
        # The preview exporter regression tests also compile the C core.
        problems.append('gcc is required for the C engine and preview tests. On Windows use WSL2 or Codespaces.')
    if frontend:
        if not shutil.which('npm') or not shutil.which('node'):
            problems.append('Node.js and npm are required. Use Node 24 LTS (tested).')
        elif not (FRONTEND/'node_modules').is_dir():
            problems.append('Frontend dependencies are missing. Run python run_tests.py --install.')
    return problems


def stage(name, command, cwd, env, run_dir, timeout):
    started = time.monotonic()
    log = run_dir / f'{name}.log'
    print(f'Running {name} ...', flush=True)
    try:
        with log.open('w', encoding='utf-8') as handle:
            result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                                    stdout=handle, stderr=subprocess.STDOUT, timeout=timeout)
        code = result.returncode
    except subprocess.TimeoutExpired:
        code = 124
        with log.open('a', encoding='utf-8') as handle:
            handle.write(f'\nTimed out after {timeout} seconds.\n')
    except OSError as exc:
        code = 127
        log.write_text(str(exc), encoding='utf-8')
    print(f'{name}: {"PASS" if code == 0 else "FAIL"} ({time.monotonic()-started:.1f}s); {log}', flush=True)
    if code:
        print('\n'.join(log.read_text(encoding='utf-8',errors='replace').splitlines()[-30:]),flush=True)
    return dict(name=name, exit_code=code, passed=code == 0,
                seconds=round(time.monotonic()-started, 3), log=str(log.relative_to(ROOT)))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true',help='Install Python and npm dependencies first (network required)')
    parser.add_argument('--skip-frontend',action='store_true',help='Explicitly run a partial suite without web tests/build')
    parser.add_argument('--skip-algorithm',action='store_true',help='Skip independent stress/calibration suite; preview still needs gcc')
    parser.add_argument('--timeout',type=int,default=600,help='Seconds per stage (default 600)')
    args=parser.parse_args(argv)
    if args.timeout < 1: parser.error('--timeout must be positive')
    parent=ROOT/'test-results';parent.mkdir(exist_ok=True)
    run_dir=Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_'),dir=parent))
    env=os.environ.copy()
    # Do not inherit a user's real database path. All test output is disposable.
    for key in ['PARSEC_DB_PATH','PARSEC_DEMO','PARSEC_PHASE2_CONFIG','PARSEC_PREVIEW_DIR','PARSEC_BIN']:
        env.pop(key,None)
    env['PARSEC_DATA_DIR']=str(run_dir/'data')
    env['PYTHONIOENCODING']='utf-8'
    stages=[]
    npm=shutil.which('npm')
    if args.install:
        stages.append(stage('install_python',[sys.executable,'-m','pip','install','-r','requirements.txt',
                                             '-c','requirements-tested.txt'],ROOT,env,run_dir,args.timeout))
        if not args.skip_frontend:
            stages.append(stage('install_frontend',[npm or 'npm','ci','--no-audit','--no-fund'],FRONTEND,env,run_dir,args.timeout))
    problems=preflight(not args.skip_frontend,not args.skip_algorithm)
    if any(not s['passed'] for s in stages): problems.append('Dependency installation failed; see the install log.')
    if not problems:
        stages.append(stage('python_tests',[sys.executable,'-m','pytest',*PYTEST_TARGETS,'-q',
                             f'--junitxml={run_dir/"pytest.xml"}'],ROOT,env,run_dir,args.timeout))
        if not args.skip_algorithm:
            stages.append(stage('algorithm_offline',[sys.executable,'phase2_test.py','--algorithm-only'],ROOT,env,run_dir,args.timeout))
        if not args.skip_frontend:
            stages.append(stage('frontend_tests',[npm,'test'],FRONTEND,env,run_dir,args.timeout))
            stages.append(stage('frontend_build',[npm,'run','build'],FRONTEND,env,run_dir,args.timeout))
    passed=not problems and bool(stages) and all(s['passed'] for s in stages)
    report=dict(passed=passed,full_suite=not(args.skip_frontend or args.skip_algorithm),
                preflight_errors=problems,stages=stages,python=sys.version,
                scientific_scope='Offline engineering/regression checks. Synthetic tests do not validate real NASA accuracy. '
                                 'C stress run can exit successfully with a numerical warning; inspect stress_status.json.')
    (run_dir/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for message in problems:print(message,file=sys.stderr)
    print(('PASS' if passed else 'FAIL')+': '+('full' if report['full_suite'] else 'partial')+' suite')
    print('Reports:',run_dir)
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
