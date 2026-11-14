"""NASA Earthdata acquisition through earthaccess, no raw CMR/LAADS API.
Catalog -> pair -> download -> extract in one run. No old manifest needed.
The optional archive fallback reads official directory HTML via earthaccess's
HTTPS session. It never constructs an unlisted processing timestamp.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,json,re,sys,shutil,tempfile
from html import unescape
from pathlib import Path
from urllib.parse import unquote,urlsplit,quote
from .pilotlib import parse_granule_filename, MASK_TO_GEO, validate_bbox, file_magic_ok,sha256,write_json,valid_nasa_https

ROOT=Path(__file__).resolve().parents[1]
COLLECTION={p:('002','5200','nc') if p.startswith('VNP') else ('061','61','hdf') for p in (*MASK_TO_GEO,*MASK_TO_GEO.values())}
BASE='https://ladsweb.modaps.eosdis.nasa.gov/archive/'
NAME=re.compile(r'(?<![\w.])(?:MOD14|MYD14|MOD03|MYD03|VNP14IMG|VNP03IMG)\.A\d{7}\.\d{4}\.\d{3}\.\d{13}\.(?:hdf|nc)(?![\w.])')
STAMP=re.compile(r'(?:MOD14|MYD14|MOD03|MYD03|VNP14IMG|VNP03IMG)\.A\d{7}\.\d{4}\.\d{3}\.',re.I)

def identity(text,product):
    """Read acquisition key even when metadata has no file suffix."""
    name=unquote(str(text)).rsplit('/',1)[-1]
    try:r=parse_granule_filename(name)
    except ValueError:
        # Some GranuleUR values end immediately after collection code.
        try:r=parse_granule_filename(name+'.')
        except ValueError:return None
    return r if r['product']==product and r['collection_code']==COLLECTION[product][0] else None

def key(r):return r['product'],r['stamp'],r['collection_code']

def science_link(url,product):
    if not isinstance(url,str) or not valid_nasa_https(url):return None
    u=urlsplit(url);filename=unquote(u.path.rsplit('/',1)[-1]);r=identity(filename,product)
    if not r or not NAME.fullmatch(filename) or any(t in u.path.lower() for t in ('opendap','/browse/','/metadata/')):return None
    if not filename.endswith('.'+COLLECTION[product][2]):return None
    return {**r,'url':url,'url_source':'earthaccess_data_links'}

def normalize(granule,product):
    umm=granule.get('umm',{}); meta=granule.get('meta',{}); provider=meta.get('provider-id') or meta.get('provider_id') or 'LAADS'
    ids=[umm.get('GranuleUR','')]+[x.get('Identifier','') for x in umm.get('DataGranule',{}).get('Identifiers',[]) if isinstance(x,dict)]
    ids += [x.get('Name','') for x in umm.get('DataGranule',{}).get('ArchiveAndDistributionInformation',[]) if isinstance(x,dict)]
    candidates=[r for s in ids if (r:=identity(s,product))]
    links=granule.data_links(access='external') or []
    direct=[r for url in links if (r:=science_link(url,product))]
    # Prefer the science file link's actual name; do not require the CMR ID to equal it.
    keys={key(r) for r in candidates}
    if keys:direct=[r for r in direct if key(r) in keys]
    if direct:
        r=sorted(direct,key=lambda x:('ladsweb' not in x['url'],x['filename']))[0]
    elif candidates:
        r={**candidates[0],'url':None,'url_source':'unresolved'}
    else:return None
    return {**r,'provider':provider,'cmr_id':meta.get('concept-id',''),'catalog_ur':umm.get('GranuleUR','')}

def dedup(records):
    out={}
    for r in records:
        k=key(r)
        if k not in out or (r.get('url') and not out[k].get('url')):out[k]=r
    return list(out.values())

def candidate_pairs(records):
    by={key(r):r for r in dedup(records)}; out=[]
    for (p,stamp,c),r in by.items():
        if p in MASK_TO_GEO and (MASK_TO_GEO[p],stamp,c) in by:
            out.append({'sensor':'VIIRS' if p=='VNP14IMG' else 'MODIS','stamp':stamp,'timestamp_utc':r['timestamp_utc'],'mask':r,'geo':by[MASK_TO_GEO[p],stamp,c]})
    return sorted(out,key=lambda x:x['timestamp_utc'])

def archive_dir(r):
    p=r['product'];date=r['stamp'][1:8];return f'{BASE}allData/{COLLECTION[p][1]}/{p}/{date[:4]}/{date[4:]}/'

def listing_names(html):return sorted(set(NAME.findall(unquote(unescape(html)))))

def resolve(r,names):
    files=[n for n in names if (i:=identity(n,r['product'])) and key(i)==key(r) and n.endswith('.'+COLLECTION[r['product']][2])]
    exact=[n for n in files if n==r['filename'] or n==r['filename']+'.'+COLLECTION[r['product']][2]]
    if exact:name=exact[0]
    elif len(set(files))==1:name=files[0]
    else:return None
    x={**r,**parse_granule_filename(name),'url':archive_dir(r)+quote(name),'provider':'LAADS','url_source':'LAADS_directory_listing_via_earthaccess_session'}
    if name!=r['filename']:
        x['original_cmr_id']=x.pop('cmr_id','');x['original_catalog_filename']=r['filename'];x['cmr_id']=''
    return x

def resolve_pairs(records,session_factory,per_sensor=1):
    candidates=candidate_pairs(records);cache={};session=None
    result=[];used=set();failures=[]
    def fix(r):
        nonlocal session
        if r.get('url'):return r
        directory=archive_dir(r)
        if directory not in cache:
            try:
                if session is None:session=session_factory()
                print('Resolving missing science link in',directory,flush=True)
                response=session.get(directory,timeout=45)
                response.raise_for_status()
                if not valid_nasa_https(response.url):raise ValueError('archive redirected outside NASA')
                cache[directory]=listing_names(response.text)
            except Exception as e:
                print('Archive listing unavailable:',type(e).__name__,flush=True);cache[directory]=[]
        return resolve(r,cache[directory])
    # Select close nominal times, but this is not footprint alignment.
    mod=[x for x in candidates if x['sensor']=='MODIS'];viirs=[x for x in candidates if x['sensor']=='VIIRS']
    if not mod or not viirs:raise ValueError('No catalog mask/geolocation pair for both sensors. Check product/version counts or use local files.')
    def seconds(x):return dt.datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00')).timestamp()
    # Rank by presence of actual data links, then best cross-sensor nominal time.
    for group,other in [(mod,viirs),(viirs,mod)]:
        group.sort(key=lambda x:(-sum(bool(x[z].get('url')) for z in ('mask','geo')),min(abs(seconds(x)-seconds(y)) for y in other)))
        accepted=0
        for pair in group:
            mask=fix(pair['mask']);geo=fix(pair['geo'])
            if not mask or not geo:
                failures.append(pair['stamp']);continue
            if mask['filename'] in used or geo['filename'] in used:continue
            result.append({**pair,'mask':mask,'geo':geo});used.update([mask['filename'],geo['filename']]);accepted+=1
            if accepted==per_sensor:break
        if accepted<per_sensor:raise ValueError(f'Only {accepted}/{per_sensor} resolved {group[0]["sensor"]} pairs. NASA catalog/listing lacks a unique science file; use local mode. Failed candidate count={len(failures)}')
    return result

def download_one(ea,record,folder):
    filename=record['filename'];target=folder/filename;folder.mkdir(parents=True,exist_ok=True)
    # Each download gets a fresh temp directory, so stale output cannot pass.
    with tempfile.TemporaryDirectory(dir=folder,prefix='download_') as temp:
        temp=Path(temp)
        try:
            paths=ea.download([record['url']],local_path=str(temp),provider=record['provider'],threads=1)
            found=[Path(x) for x in (paths or []) if x and Path(x).name==filename and file_magic_ok(x)]
            if len(found)!=1:raise ValueError('earthaccess returned no matching valid science file')
            # Format magic alone is not proof of semantic validity; extractor subsequently opens the arrays.
            shutil.move(str(found[0]),target)
        except Exception as e:
            # The earthaccess authenticated HTTPS session also handles the explicit
            # LAADS URLs when provider-specific routing/download is unsuccessful.
            print('earthaccess.download failed; trying its authenticated HTTPS session:',type(e).__name__,flush=True)
            sess=ea.get_requests_https_session();tmp=temp/filename
            with sess.get(record['url'],stream=True,timeout=(30,180)) as response:
                response.raise_for_status()
                if not valid_nasa_https(response.url):raise ValueError('download redirected outside NASA')
                with tmp.open('wb') as fp:
                    for chunk in response.iter_content(1024*1024):
                        if chunk:fp.write(chunk)
            if not file_magic_ok(tmp):raise ValueError('NASA response is not HDF/NetCDF; verify account authorization')
            shutil.move(str(tmp),target)
    return {'filename':filename,'bytes':target.stat().st_size,'sha256':sha256(target),'url':record['url'],'provider':record['provider']}

def acquire(ea,args):
    from . import audit
    out=args.out;out.mkdir(parents=True,exist_ok=False);raw=out/'raw_l2'
    # Eliminate stale success artifacts before a new attempt.
    for p in ['catalog.json','pair_plan.json','download_receipts.json','SUCCESS.json']:(out/p).unlink(missing_ok=True)
    if (out/'extracted'/'pilot_audit.json').exists():(out/'extracted'/'pilot_audit.json').unlink()
    records=[];counts={}
    start=dt.date.fromisoformat(args.start);end=dt.date.fromisoformat(args.end)
    if not start<end or (end-start).days>31:raise ValueError('pilot needs an exclusive end date within 31 days of start')
    bounds=validate_bbox(args.bbox)
    temporal=(start.isoformat()+'T00:00:00Z',(end-dt.timedelta(days=1)).isoformat()+'T23:59:59Z')
    for prod in COLLECTION:
        granules=ea.search_data(short_name=prod,temporal=temporal,bounding_box=tuple(bounds),count=args.limit)
        rec=[r for g in granules if (r:=normalize(g,prod))]
        counts[prod]={'catalog_hits_returned':len(granules),'recognized_collection':len(rec),'science_links':sum(bool(r['url']) for r in rec)}
        print(prod,counts[prod],flush=True);records.extend(rec)
        if len(granules)>=args.limit:print('WARNING: search limit reached; this pilot is not an exhaustive sample.')
    write_json(out/'catalog.json',{'counts':counts,'records':records,'bbox_wsen':bounds,'temporal':temporal})
    if not candidate_pairs(records):raise ValueError('No compatible catalog pairs found; inspect catalog.json')
    # No token is manually exported; use earthaccess credentials and library auth.
    auth=ea.login(strategy=args.login,persist=False)
    if not auth.authenticated:raise ValueError('Earthdata login was unsuccessful')
    pairs=resolve_pairs(records,ea.get_requests_https_session,args.per_sensor)
    plan={'bbox_wsen':bounds,'pairs':pairs,'both_sensors_selected':True,'warning':'Nominal acquisition times; no cross-sensor footprint alignment verified.'}
    write_json(out/'pair_plan.json',plan)
    receipts=[]
    for pair in pairs:
        for name in ('mask','geo'):
            r=pair[name];print('Downloading',r['filename'],flush=True);receipts.append(download_one(ea,r,raw))
    if len(receipts)!=4*args.per_sensor:raise ValueError('download count mismatch')
    write_json(out/'download_receipts.json',{'files':receipts,'count':len(receipts),'source':'earthaccess'})
    summaries=audit.run(plan,raw,out/'extracted',ROOT/'nasa/extract.py',bounds)
    if {s['sensor'] for s in summaries}!={'MODIS','VIIRS'}:raise ValueError('both sensors required')
    write_json(out/'SUCCESS.json',{'downloaded':len(receipts),'audited':len(summaries),'scientific_status':'AUTHENTIC DOWNLOAD AND MASK AUDIT ONLY; not calibrated'})
    print('PASS: real Earthdata download and coverage audit:',len(receipts),'files')

def local(args):
    from . import audit
    bounds=validate_bbox(args.bbox);out=args.out;out.mkdir(parents=True,exist_ok=False)
    (out/'SUCCESS.json').unlink(missing_ok=True)
    records=[];source={}
    for path in args.files:
        path=path.resolve()
        r=parse_granule_filename(path.name)
        if not NAME.fullmatch(path.name) or r['product'] not in COLLECTION or r['collection_code']!=COLLECTION[r['product']][0] or not file_magic_ok(path):raise ValueError('invalid science filename, collection or file format: '+path.name)
        records.append(r);source[path.name]=path
    pairs=candidate_pairs(records)
    if len(records) not in (4,8) or len(pairs)*2!=len(records) or {x['sensor'] for x in pairs}!={'MODIS','VIIRS'} or len({r['filename'] for r in records})!=len(records):raise ValueError('four or eight distinct local files forming complete mask/geo pairs from both sensors required')
    # Audit expects a common data directory. Copy into dedicated output (no overwrite of user inputs).
    raw=out/'raw_l2';raw.mkdir(exist_ok=True)
    for name,path in source.items():
        if (raw/name).resolve()!=path:shutil.copy2(path,raw/name)
    plan={'bbox_wsen':bounds,'pairs':pairs,'both_sensors_selected':True};write_json(out/'pair_plan.json',plan)
    summaries=audit.run(plan,raw,out/'extracted',ROOT/'nasa/extract.py',bounds)
    write_json(out/'SUCCESS.json',{'audited':len(summaries),'scientific_status':'LOCAL FILE FORMAT AND COVERAGE AUDIT ONLY; provenance must be supplied separately'})
    print('PASS: local-file audit; NASA provenance not independently verified')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('live');a.add_argument('--start',default='2023-07-01');a.add_argument('--end',default='2023-07-08',help='exclusive UTC date');a.add_argument('--limit',type=int,default=300);a.add_argument('--per-sensor',type=int,choices=[1,2],default=1);a.add_argument('--login',choices=['interactive','all','netrc','environment'],default='interactive')
    b=sub.add_parser('local');b.add_argument('files',nargs='+',type=Path)
    for parser in (a,b):parser.add_argument('--bbox',nargs=4,type=float,default=[-139,48,-114,60]);parser.add_argument('--out',type=Path,default=ROOT/'output/earthdata')
    args=p.parse_args(argv)
    try:
        if args.mode=='local':local(args)
        else:
            if not 1<=args.limit<=1000:raise ValueError('limit must be 1..1000')
            import earthaccess
            acquire(earthaccess,args)
    except Exception as e:
        # Avoid dumping session headers, token strings, or full credential-bearing exceptions.
        if isinstance(e,(ValueError,FileNotFoundError,ImportError)):print('ERROR:',e,file=sys.stderr)
        else:print('ERROR:',type(e).__name__, '(check NASA service, account authorization and connectivity)',file=sys.stderr)
        return 2
    return 0

if __name__=='__main__':sys.exit(main())

