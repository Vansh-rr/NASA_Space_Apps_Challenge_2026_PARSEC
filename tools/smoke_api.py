"""Smoke-test a deployed API using the standard library only."""
from __future__ import annotations
import argparse
import json
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


def origin_url(value, *, allow_http=False):
    u=urlsplit(value.strip())
    if u.scheme not in (('https','http') if allow_http else ('https',)) or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
        raise ValueError('Use an HTTPS origin without a path, credentials, query or fragment.')
    return f'{u.scheme}://{u.netloc}'


def smoke(base, *, origin=None, expect_demo=False, wait_seconds=0):
    base=origin_url(base,allow_http=True)
    deadline=time.monotonic()+wait_seconds
    while True:
        try:
            with urlopen(base+'/health',timeout=15) as res: health=json.load(res)
            break
        except (URLError,HTTPError):
            if time.monotonic()>=deadline:raise
            time.sleep(1)
    if health.get('database_found') is not True or health.get('observations',0)<=0 or health.get('demo') is not expect_demo:
        raise ValueError('Health response lacks observations or has the wrong real/demo provenance.')
    endpoints=['/regions','/observations?sensor=MODIS&limit=1','/activity?sensor=MODIS',
               '/comparison?sample=1','/history?month=7','/model-preview/metadata','/model-preview/field?limit=1']
    checks=[]
    for path in endpoints:
        req=Request(base+path,headers={'Origin':origin} if origin else {})
        with urlopen(req,timeout=30) as res:
            data=json.load(res)
            if origin and res.headers.get('Access-Control-Allow-Origin')!=origin:
                raise ValueError('Allowed frontend origin did not receive the correct CORS header.')
            if path.startswith('/observations') and not data:
                raise ValueError('No MODIS observations for the frontend default month.')
            if path.startswith('/comparison'):
                h=next((s for s in data['sensors'] if s['sensor']=='harmonized'),None)
                if not h or h['detections']<=0:raise ValueError('No harmonized predictions visible to the API.')
            checks.append(dict(path=path,status=res.status))
    if origin:
        with urlopen(Request(base+'/health',headers={'Origin':'https://unrelated.invalid'}),timeout=15) as res:
            if res.headers.get('Access-Control-Allow-Origin') is not None:
                raise ValueError('CORS still permits an unrelated origin.')
    return dict(passed=True,health=health,checks=checks)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--api-url',required=True)
    p.add_argument('--frontend-origin')
    p.add_argument('--expect-demo',action='store_true',help='Only for CI/local synthetic containers')
    p.add_argument('--wait-seconds',type=int,default=0)
    a=p.parse_args(argv)
    try:
        origin=origin_url(a.frontend_origin) if a.frontend_origin else None
        print(json.dumps(smoke(a.api_url,origin=origin,expect_demo=a.expect_demo,wait_seconds=a.wait_seconds),indent=2))
        return 0
    except Exception as exc:
        print(f'API smoke check failed: {exc}')
        return 1


if __name__=='__main__':raise SystemExit(main())
