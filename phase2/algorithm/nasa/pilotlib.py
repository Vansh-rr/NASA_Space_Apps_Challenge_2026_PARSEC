"""Pure helpers for PARSEC real Level-2 pilot; never fabricates independent truth."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

MASK_TO_GEO = {'MOD14':'MOD03', 'MYD14':'MYD03', 'VNP14IMG':'VNP03IMG'}
PRODUCTS = set(MASK_TO_GEO) | set(MASK_TO_GEO.values())
PATTERN = re.compile(r'^(MOD14|MYD14|MOD03|MYD03|VNP14IMG|VNP03IMG)\.A(\d{7})\.(\d{4})\.([0-9A-Za-z]+)\.', re.I)
EXTS={'.hdf','.nc','.nc4','.h5','.hdf5'}


def parse_granule_filename(filename):
    filename=Path(filename).name
    m=PATTERN.match(filename)
    if not m: raise ValueError('Unrecognized MODIS/VIIRS Level-2 filename: '+filename)
    product, yday, hm, version = m.groups()
    year=int(yday[:4]); doy=int(yday[4:]); hour=int(hm[:2]); minute=int(hm[2:])
    days=366 if year % 4==0 and (year %100 !=0 or year %400==0) else 365
    if not (1<=doy<=days and hour<24 and minute<60):
        raise ValueError('Invalid acquisition timestamp in '+filename)
    timestamp=(dt.datetime(year,1,1,tzinfo=dt.timezone.utc)+dt.timedelta(days=doy-1,hours=hour,minutes=minute))
    return {'product':product.upper(), 'stamp':f'A{yday}.{hm}', 'collection_code':version,
            'timestamp_utc':timestamp.isoformat().replace('+00:00','Z'), 'filename':filename}


def validate_bbox(bbox):
    if len(bbox)!=4:raise ValueError('bbox requires W S E N')
    w,s,e,n=map(float,bbox)
    if not (-180<=w<e<=180 and -90<=s<n<=90):raise ValueError('Bad bbox: need W < E and S < N')
    return [w,s,e,n]


def valid_nasa_https(url):
    try:
        u=urlparse(url)
        h=(u.hostname or '').lower()
        return u.scheme=='https' and (h=='nasa.gov' or h.endswith('.nasa.gov')) and not u.username and not u.password
    except (ValueError,TypeError):
        return False


def file_magic_ok(path):
    p=Path(path)
    if not p.is_file() or p.stat().st_size<8:return False
    with p.open('rb') as f: head=f.read(8)
    return head.startswith(b'\x89HDF\r\n\x1a\n') or head.startswith(b'\x0e\x03\x13\x01') or head.startswith(b'CDF')


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def write_json(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))
