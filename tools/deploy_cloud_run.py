"""Deploy the prepared real-data API to an explicitly selected Google Cloud project."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.preflight_deploy import check_snapshot
from tools.smoke_api import origin_url, smoke


def build_command(project,region,service,frontend_origin=None,*,cors_only=False):
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]',project):raise ValueError('Use the actual Google Cloud project ID, not its display name.')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,61}[a-z0-9]|[a-z]',service):raise ValueError('Invalid Cloud Run service name')
    if not re.fullmatch(r'[a-z]+-[a-z]+[0-9]',region):raise ValueError('Invalid Cloud Run region')
    origin=origin_url(frontend_origin) if frontend_origin else ''
    settings='^@^PARSEC_CORS_ORIGINS='+origin+'@PARSEC_DEMO=0@PARSEC_DB_PATH=/app/data/fires.duckdb@PARSEC_PREVIEW_DIR=/app/model_preview/bc-july-2023'
    command=['gcloud','run','services','update' if cors_only else 'deploy',service] if cors_only else ['gcloud','run','deploy',service]
    if not cors_only:
        command += ['--source',str(ROOT),'--memory','1Gi','--cpu','1','--min-instances','0','--max-instances','1','--concurrency','4','--allow-unauthenticated']
    return command+['--project',project,'--region',region,'--update-env-vars',settings]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',required=True)
    p.add_argument('--region',default='europe-west1')
    p.add_argument('--service',default='parsec-api')
    p.add_argument('--frontend-origin')
    p.add_argument('--cors-only',action='store_true',help='Update the allowed site without uploading the database again')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args(argv)
    try:
        if a.cors_only and not a.frontend_origin:raise ValueError('--cors-only requires --frontend-origin')
        command=build_command(a.project,a.region,a.service,a.frontend_origin,cors_only=a.cors_only)
        if a.dry_run:
            print(json.dumps({'command':command,'executed':False},indent=2));return 0
        if not shutil.which('gcloud'):raise ValueError('Install the gcloud CLI and authenticate with gcloud auth login first.')
        if not a.cors_only:print(json.dumps(check_snapshot(ROOT/'data/fires.duckdb'),indent=2))
        subprocess.run(command,cwd=ROOT,check=True)
        url=subprocess.check_output(['gcloud','run','services','describe',a.service,'--project',a.project,
            '--region',a.region,'--format=value(status.url)'],cwd=ROOT,text=True).strip()
        report=smoke(url,origin=origin_url(a.frontend_origin) if a.frontend_origin else None,wait_seconds=30)
        report.update(api_url=url,frontend_origin=a.frontend_origin)
        (ROOT/'deployment.local.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2));return 0
    except Exception as exc:
        print(f'Deployment failed: {exc}',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
