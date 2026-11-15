"""Thin command orchestration; never changes the scientific algorithm."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
ALGORITHM = ROOT / 'phase2' / 'algorithm'


def data_root():
    return Path(os.environ.get('PARSEC_DATA_DIR', ROOT / 'data')).expanduser().resolve()


def fresh(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_'), dir=root))


def execute(args, *, env=None):
    args = [str(a) for a in args]
    print('+', ' '.join(args), flush=True)
    return subprocess.run(args, cwd=ROOT, env=env).returncode


def verify_algorithm():
    for line in (ALGORITHM / 'SHA256SUMS').read_text().splitlines():
        expected, path = line.split('  ', 1)
        actual = hashlib.sha256((ALGORITHM / path).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f'Algorithm source differs from uploaded branch: {path}')
    print('PASS: unchanged algorithm source checksums', flush=True)


def add_algorithm_options(p):
    src = p.add_mutually_exclusive_group()
    src.add_argument('--nasa-csv-dir', type=Path, help='Existing extracted Level-2 pixel CSV directory')
    src.add_argument('--nasa-raw-dir', type=Path, help='Existing NASA mask/geolocation science files')
    src.add_argument('--nasa-live', action='store_true', help='Acquire NASA granules using Earthdata login')
    src.add_argument('--reviewed-data', type=Path, help='Directory containing all six reviewed reference inputs')
    p.add_argument('--nasa-start', default='2023-07-01')
    p.add_argument('--nasa-end', default='2023-07-08')
    p.add_argument('--nasa-bbox', nargs=4, type=float, default=[-139, 48, -114, 60])
    p.add_argument('--per-sensor', type=int, choices=[1, 2], default=2)
    p.add_argument('--max-folds', type=int, default=4)
    p.add_argument('--particles', type=int, default=5000)
    p.add_argument('--login', choices=['interactive', 'all', 'netrc', 'environment'], default='interactive')
    p.add_argument('--install', action='store_true', help='Install dependencies in the active Python environment')


def algorithm_mode(args):
    if args.reviewed_data:
        return 'reviewed'
    if args.nasa_csv_dir or args.nasa_raw_dir or args.nasa_live:
        return 'nasa'
    return None


def algorithm_command(stage, args, out_root):
    cmd = [sys.executable, ALGORITHM / 'test_parsec_independent.py', stage,
           '--out-root', Path(out_root).resolve(), '--particles', args.particles]
    if stage == 'reviewed':
        cmd += ['--data-dir', args.reviewed_data.resolve()]
    if stage == 'nasa':
        cmd += ['--max-folds', args.max_folds, '--full', '--start', args.nasa_start,
                '--end', args.nasa_end, '--bbox', *args.nasa_bbox,
                '--per-sensor', args.per_sensor, '--login', args.login]
        if args.nasa_csv_dir:
            cmd += ['--csv-dir', args.nasa_csv_dir.resolve()]
        elif args.nasa_raw_dir:
            cmd += ['--raw-dir', args.nasa_raw_dir.resolve()]
        elif args.nasa_live:
            cmd += ['--live']
    return cmd


def install(args, *, engineering=True):
    if not args.install:
        return 0
    req = ROOT / 'requirements.txt' if engineering else ALGORITHM / 'requirements.txt'
    rc = execute([sys.executable, '-m', 'pip', 'install', '-r', req])
    if not rc and (args.nasa_live or args.nasa_raw_dir):
        rc = execute([sys.executable, '-m', 'pip', 'install', '-r', ALGORITHM / 'requirements-nasa.txt'])
    return rc


def write_status(run, stages):
    report = {'stages': stages, 'all_requested_stages_passed': bool(stages) and all(v == 0 for v in stages.values()),
              'algorithm_scope': 'Offline synthetic, NASA mask prediction, or reviewed reference according to requested stage; see individual reports.'}
    (run / 'workflow_status.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('Workflow reports:', run)
    return 0 if report['all_requested_stages_passed'] else 1
