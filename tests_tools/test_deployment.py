"""Deployment checks run offline and never contact Google Cloud."""
from pathlib import Path
import pytest
from tools.deploy_cloud_run import build_command,main
from tools.preflight_deploy import check_snapshot
from tools.smoke_api import origin_url
from tools.record_live_demo import demo_section
from phase3.api import cors_origins


def test_cloud_run_command_is_project_scoped_and_limits_instances():
    command=build_command('parsec-firesync','europe-west1','parsec-api','https://parsec.pages.dev/')
    assert command[:4]==['gcloud','run','deploy','parsec-api']
    assert command[command.index('--project')+1]=='parsec-firesync'
    assert command[command.index('--max-instances')+1]=='1'
    assert 'PARSEC_CORS_ORIGINS=https://parsec.pages.dev@' in command[-1]
    assert 'PARSEC_DEMO=0' in command[-1]
    assert not any('FIRMS_MAP_KEY' in x or 'password' in x for x in command)


def test_cors_only_does_not_upload_database():
    command=build_command('parsec-firesync','europe-west1','parsec-api','https://parsec.pages.dev',cors_only=True)
    assert command[:5]==['gcloud','run','services','update','parsec-api']
    assert '--source' not in command


def test_empty_cors_starts_closed_and_explicit_origins_are_normalized():
    assert cors_origins('')==[]
    assert cors_origins(' https://parsec.pages.dev/ , https://parsec.pages.dev ')==['https://parsec.pages.dev']
    for value in ['https://site.example/path','https://user:pass@site.example','*,https://site.example']:
        with pytest.raises(ValueError):cors_origins(value)


def test_invalid_production_origins_and_project_names_fail():
    for value in ['http://site.example','/api','https://user:pass@site.example','https://site.example/path']:
        with pytest.raises(ValueError):origin_url(value)
    with pytest.raises(ValueError):build_command('My Project Name','europe-west1','parsec-api')


def test_dry_run_never_calls_gcloud(monkeypatch):
    import tools.deploy_cloud_run as deploy
    monkeypatch.setattr(deploy.subprocess,'run',lambda *a,**k:pytest.fail('gcloud must not run'))
    assert main(['--project','parsec-firesync','--dry-run'])==0


def test_snapshot_must_exist_and_be_self_contained(tmp_path):
    with pytest.raises(ValueError,match='regular'):check_snapshot(tmp_path/'missing.duckdb')
    db=tmp_path/'fires.duckdb';db.touch();Path(str(db)+'.wal').touch()
    with pytest.raises(ValueError,match='WAL'):check_snapshot(db)


def test_snapshot_without_real_predictions_is_rejected(tmp_path):
    from phase2.phase2_database import connect
    db=tmp_path/'demo.duckdb'
    with connect(db) as con:
        # Observation inputs are fabricated for this test only.
        con.execute("INSERT INTO observations (observation_id,schema_version,sensor_family,instrument,satellite,acq_datetime_utc,acq_date,latitude,longitude,frp_mw) VALUES ('m',1,'MODIS','MODIS','Aqua','2023-07-01 12:00:00+00','2023-07-01',53,-122,10), ('v',1,'VIIRS','VIIRS','S-NPP','2023-07-01 12:05:00+00','2023-07-01',53,-122,5)")
    with pytest.raises(ValueError,match='real model run'):check_snapshot(db)


def test_readme_urls_are_actual_origins():
    section=demo_section('https://parsec.pages.dev','https://parsec-api-example.run.app')
    assert 'https://parsec.pages.dev' in section and 'https://parsec-api-example.run.app/docs' in section
    assert 'physical accuracy is unvalidated' in section


def test_upload_context_excludes_secrets_but_keeps_the_database(tmp_path):
    import subprocess
    root=Path(__file__).resolve().parents[1]
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'.gitignore').write_text((root/'.gcloudignore').read_text())
    included=['Dockerfile','.dockerignore','requirements-api.txt','requirements-tested.txt',
              'phase1_database.py','phase1_downloader.py','phase2/phase2_config.py',
              'phase2/model_preview.py','phase3/api.py','configs/phase2.yaml',
              'model_preview/bc-july-2023/manifest.json','data/fires.duckdb']
    excluded=['.env','.env.local','.netrc','service-account.json','README.md',
              'firesync-app/.env.local','data/fires.duckdb.wal','data/demo_fires.duckdb',
              'data/raw/sample.csv','phase2/__pycache__/phase2_config.pyc',
              'tests_phase2/test_phase2_pipeline.py','tools/deploy_cloud_run.py',
              'model_preview/service-account.json','model_preview/bc-july-2023/private-key.pem']
    for name in included+excluded:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
        code=subprocess.run(['git','check-ignore','--no-index','-q',name],cwd=tmp_path).returncode
        assert code == (0 if name in excluded else 1),name
    assert (root/'.gcloudignore').read_text()==(root/'.dockerignore').read_text()


def test_container_startup_connection_reset_is_retried(monkeypatch):
    import io,json
    import tools.smoke_api as api
    health_calls=[]
    class Response(io.BytesIO):
        status=200
        headers={}
    def open_response(request,timeout):
        url=request if isinstance(request,str) else request.full_url
        if url.endswith('/health'):
            health_calls.append(url)
            if len(health_calls)==1:raise ConnectionResetError('Container is still starting')
            data={'status':'ok','database_found':True,'observations':1,'demo':False}
        elif '/comparison?' in url:data={'sensors':[{'sensor':'harmonized','detections':1}]}
        elif '/observations?' in url:data=[{'id':'example'}]
        else:data={}
        return Response(json.dumps(data).encode())
    monkeypatch.setattr(api,'urlopen',open_response)
    monkeypatch.setattr(api.time,'sleep',lambda _:None)
    assert api.smoke('https://api.example',wait_seconds=2)['passed'] is True
    assert len(health_calls)==2
