"""Publish a compact, read-only PARSEC grid preview; never change the C core.
Run as python -m phase2.model_preview. See docs/MODEL_PREVIEW.md.
"""
from __future__ import annotations
import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ALGO = ROOT / 'phase2' / 'algorithm'
SOURCE_SHA = 'c6349192685a304e5c6d4e04c28b11bdadac60f05274528e3fd67e4413570890'
DISCLAIMER = ('Exploratory NASA fire-mask reconstruction; approximate footprints, nominal granule times, '
              'illustrative calibration. FRP is a model-dependent proxy, not a validated physical retrieval. '
              'Not a full-region or full-month reconstruction. Holdout scores measure detection agreement only.')


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    Path(path).write_text(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc(s):
    t = datetime.fromisoformat(s.replace('Z', '+00:00'))
    require(t.tzinfo is not None, 'UTC offset required')
    return t.astimezone(timezone.utc)


def verify_algorithm():
    require(sha(ALGO / 'parsec.c') == SOURCE_SHA, 'Unexpected C source; refusing publication')
    from phase2.workflow import verify_algorithm as verify
    verify()


def load_candidate(run, fold):
    """Return a full reconstruction from a fixed fold index, not the best score."""
    from phase2.algorithm.prepare import compiled, write_field
    work = run / f'fold_{fold:02d}'
    inp, fit = work / 'input', work / 'full_reconstruction'
    bundle, report = read(inp / 'bundle.json'), read(fit / 'report.json')
    require(bundle['source_kind'] == report['source_kind'] == 'NASA_MASK_EXPLORATORY', 'not a NASA mask pilot')
    require(report['calibration_kind'] == 'ILLUSTRATIVE' and report['warning'] is False, 'not a reliable illustrative reconstruction')
    require(report['train_modis'] > 0 and report['train_viirs'] > 0, 'full fit needs both sensor families')
    require(report['holdout_modis'] == report['holdout_viirs'] == 0, 'not a full-observation reconstruction')
    # Verify exact numeric input against the geometry in the same fold.
    data, _ = compiled(bundle, exploratory=True)
    full = dict(data, observations=[dict(o, holdout=False) for o in data['observations']])
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'field.txt'
        write_field(target, full)
        require(sha(target) == sha(inp / 'field_all.txt'), 'bundle/full numeric input mismatch')
        write_field(target, data)
        require(sha(target) == sha(inp / 'field.txt'), 'bundle/holdout numeric input mismatch')
    return work, bundle, full, report


def build_payload(bundle, data, fit, run_id):
    """Join C rows to grid geometry, never rescale or recompute posterior values."""
    from shapely.geometry import shape, mapping
    from shapely.ops import transform
    from pyproj import Transformer
    report = read(fit / 'report.json')
    require(report['source_kind'] == data['source_kind'], 'source mismatch')
    require(report['warning'] is False, 'numerical warning; refuse publication')
    require(report['cells'] == len(data['cells']) and report['time_bins'] == len(data['times']), 'dimension mismatch')
    require(not any(o.get('holdout') for o in data['observations']), 'display input must be full fit')
    counts = Counter(o['sensor'] for o in data['observations'] if o['usable'])
    require(counts['modis'] == report['train_modis'] and counts['viirs'] == report['train_viirs'], 'sensor counts mismatch')
    require(all(counts[s] > 0 for s in ('modis', 'viirs')), 'both training sensors required')
    forward = Transformer.from_crs(4326, bundle['area_crs'], always_xy=True).transform
    backward = Transformer.from_crs(bundle['area_crs'], 4326, always_xy=True).transform
    geoms, centres, bounds = [], {}, []
    for c in bundle['cells']:
        g = shape(c['geometry']); ident = c['cell_id']
        pt = transform(backward, transform(forward, g).centroid)
        centres[ident] = (pt.y, pt.x); bounds.append(g.bounds)
        geoms.append(dict(type='Feature', id=ident, geometry=mapping(g), properties=dict(cell_id=ident, latitude=pt.y, longitude=pt.x)))
    require(set(centres) == set(data['cells']), 'geometry IDs differ')
    support = Counter((o['time_index'], data['cells'][i]) for o in data['observations'] if o['usable'] for i in o['indices'])
    times = {utc(t): i for i,t in enumerate(data['times'])}
    fields, seen = [], set()
    keys = ('p_fire','mean_frp_mw','ci95_low_mw','ci95_high_mw','within_variance_mw2','between_variance_mw2')
    with (fit / 'field_posterior.csv').open(newline='') as f:
        for row in csv.DictReader(f):
            t, ident = utc(row['time']), row['cell_id']
            require(t in times and ident in centres and (t, ident) not in seen, 'unexpected/duplicate cell-time row')
            seen.add((t,ident)); vals = {k:float(row[k]) for k in keys}
            require(all(math.isfinite(v) and v >= 0 for v in vals.values()), 'invalid posterior number')
            require(vals['p_fire'] <= 1 and vals['ci95_low_mw'] <= vals['ci95_high_mw'], 'invalid posterior bounds')
            require(vals['mean_frp_mw'] <= max(data['levels_mw']) + 1e-8 and vals['ci95_high_mw'] <= max(data['levels_mw']) + 1e-8, 'posterior outside intensity support')
            n = int(row['usable_observation_count']); require(n == support[times[t], ident], 'usable support mismatch')
            lat,lon = centres[ident]
            fields.append(dict(time=row['time'],cell_id=ident,latitude=lat,longitude=lon,**vals,
                usable_observation_count=n,coverage_status='observed' if n else 'model_only',
                source_kind=report['source_kind'],calibration_kind=report['calibration_kind'],
                physical_frp_validated=False,warning=False,model_run_id=run_id))
    require(len(seen) == len(times)*len(centres), 'incomplete cell-time grid')
    fields.sort(key=lambda r:(utc(r['time']),r['cell_id']))
    bbox=[min(b[0] for b in bounds),min(b[1] for b in bounds),max(b[2] for b in bounds),max(b[3] for b in bounds)]
    metadata=dict(model_run_id=run_id,source_kind=report['source_kind'],calibration_kind=report['calibration_kind'],
        physical_frp_validated=False,warning=False,solver=report['solver'],area_crs=bundle['area_crs'],
        bbox=bbox,start_utc=min(times).isoformat(),last_bin_utc=max(times).isoformat(),bin_seconds=bundle['bin_seconds'],
        cells=len(centres),time_bins=len(times),rows=len(fields),observed_rows=sum(r['usable_observation_count']>0 for r in fields),
        training_observations=dict(counts),levels_mw=data['levels_mw'],disclaimer=DISCLAIMER if report['source_kind']=='NASA_MASK_EXPLORATORY' else 'SYNTHETIC TEST ONLY')
    return metadata, fields, dict(type='FeatureCollection', features=geoms)


def publish(run, out, start, end, bbox):
    verify_algorithm()
    run, out = Path(run).resolve(), Path(out).resolve()
    require(not out.exists(), f'output exists: {out}; choose a new path')
    meta = read(run / 'run_metadata.json')
    for key, name in [('source_sha256','parsec.c'),('prepare_sha256','prepare.py'),('runner_sha256','test_parsec_independent.py')]:
        require(meta[key] == sha(ALGO/name), f'run source mismatch: {name}')
    summary = read(run/'NASA_REPORT.json'); plan=read(run/'fold_plan.json')['heldout_granules']
    require(meta['stage'] in ('nasa','all'), 'not a NASA run')
    require(len(summary['folds']) == len(plan), 'fold summary incomplete')
    failures=[]; choice=None
    for i, granule in enumerate(plan,1):
        try:
            require(summary['folds'][i-1]['granule']==granule,'fold order mismatch')
            require(summary['folds'][i-1]['status'].startswith('COMPLETED'), 'holdout inference did not complete reliably')
            work,bundle,data,report=load_candidate(run,i)
            from phase2.algorithm.prepare import utc as parse_time
            # Use actual observations, not requested month as a coverage claim.
            require(all(start<=parse_time(o['acquisition_utc']).date()<=end for o in bundle['observations']), 'observations outside requested dates')
            from shapely.geometry import shape
            w,s,e,n=bbox
            require(all(w<=shape(o['geometry']).centroid.x<=e and s<=shape(o['geometry']).centroid.y<=n for o in bundle['observations']), 'observations outside requested bbox')
            from re import fullmatch
            pattern=r'(MOD14|MYD14|VNP14IMG|VJ114IMG|VJ214IMG)\.A\d{7}\.\d{4}\.\d{3}\.\d{13}\.(hdf|nc)'
            require(all(fullmatch(pattern,o['source_granule']) for o in bundle['observations']), 'not recognized NASA granule IDs')
            geo_products={'MOD14':'MOD03','MYD14':'MYD03','VNP14IMG':'VNP03IMG','VJ114IMG':'VJ103IMG','VJ214IMG':'VJ203IMG'}
            for o in bundle['observations']:
                parts=o['source_granule'].split('.')
                geo=o.get('geolocation_granule','').split('.')
                require(len(geo)>=6 and geo[:4]==[geo_products[parts[0]],*parts[1:4]] and o.get('source_collection')==parts[3], 'mask/geolocation lineage mismatch')
            validation=read(work/'comparison_report.json')
            require(validation['source_kind']=='NASA_MASK_EXPLORATORY' and validation['numerical_warning'] is False,'holdout validation warning')
            require(set(validation['heldout_granules'])=={granule},'holdout identity mismatch')
            # Selection never uses predictive scores or class counts.
            choice=(i,work,bundle,data,report,validation);break
        except (OSError,ValueError,KeyError,TypeError) as exc:
            failures.append(dict(fold=i,granule=granule,reason=str(exc)))
    require(choice is not None, 'No eligible full reconstruction; inspect NASA_REPORT.json: '+json.dumps(failures))
    i,work,bundle,data,report,validation=choice
    fit=work/'full_reconstruction'
    run_id='parsec-'+sha(fit/'field_posterior.csv')[:12]+'-'+sha(work/'input'/'field_all.txt')[:12]
    metadata,fields,geometry=build_payload(bundle,data,fit,run_id)
    metadata.update(selection='first completed warning-free fold in original acquisition order; no score ranking',selected_fold=i,source_sha256=SOURCE_SHA,
        source_granules=sorted({o['source_granule'] for o in bundle['observations']}),requested_start=start.isoformat(),requested_end=end.isoformat(),requested_bbox=list(bbox),
        lineage='NASA-format granule IDs and local run provenance checked; source authenticity not independently attested by exporter')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.preview_',dir=out.parent) as tmp:
        d=Path(tmp)/'payload';d.mkdir()
        dump(d/'metadata.json',metadata);dump(d/'field.json',{'items':fields,'total':len(fields)});dump(d/'cells.geojson',geometry)
        dump(d/'validation.json',{'scope':'separate withheld-granule detection prediction; never scores full displayed reconstruction','selected_fold':i,'comparison':validation,'attempted_folds':[{k:v for k,v in x.items() if k!='path'} for x in summary['folds']], 'skipped_for_preview':failures})
        shutil.copyfile(fit/'field_posterior.csv',d/'field_posterior.csv');shutil.copyfile(fit/'report.json',d/'report.json')
        shutil.copyfile(work/'comparison_metrics.csv',d/'comparison_metrics.csv')
        dump(d/'manifest.json',{'model_run_id':run_id,'files':{p.name:sha(p) for p in sorted(d.iterdir())}})
        require(not out.exists(), 'output already exists');d.rename(out)
    print('Published:',out,'\n',json.dumps(metadata,indent=2))
    return out


class PreviewStore:
    """Read-only API adapter. Instantiate once; no C execution per request."""
    def __init__(self, directory):
        d=Path(directory);manifest=read(d/'manifest.json')
        required={'metadata.json','field.json','cells.geojson','validation.json','field_posterior.csv','report.json','comparison_metrics.csv'}
        require(set(manifest['files'])==required,'incomplete manifest')
        for name,expected in manifest['files'].items():require(sha(d/name)==expected,'preview hash mismatch: '+name)
        self.metadata=read(d/'metadata.json');self.rows=read(d/'field.json')['items'];self.geometry=read(d/'cells.geojson');self.validation=read(d/'validation.json')
        require(manifest['model_run_id']==self.metadata['model_run_id'] and len(self.rows)==self.metadata['rows'],'manifest metadata mismatch')
        report = read(d/'report.json')
        require(self.metadata['source_kind'] == report['source_kind']
                and self.metadata['calibration_kind'] == report['calibration_kind'], 'preview provenance mismatch')
        require(self.metadata['physical_frp_validated'] is False
                and self.metadata['warning'] is False and report['warning'] is False,
                'preview cannot claim physical validation or suppress numerical warnings')
        cells = {f['properties']['cell_id'] for f in self.geometry['features']}
        require(len(cells) == self.metadata['cells'], 'preview cell count mismatch')
        seen = set()
        for row in self.rows:
            key = (utc(row['time']), row['cell_id'])
            require(key not in seen and row['cell_id'] in cells, 'unexpected/duplicate preview row')
            seen.add(key)
            require(type(row['p_fire']) in (int, float) and math.isfinite(row['p_fire'])
                    and 0 <= row['p_fire'] <= 1, 'invalid preview probability')
            require(-90 <= row['latitude'] <= 90 and -180 <= row['longitude'] <= 180,
                    'invalid preview coordinates')
        require(len(seen) == self.metadata['cells'] * self.metadata['time_bins'], 'incomplete preview grid')

    def _select(self,start,end,bbox):
        start,end=date.fromisoformat(start),date.fromisoformat(end)
        require(start<=end and (end-start).days<=3660,'invalid date range (max 3661 days)')
        w,s,e,n=map(float,bbox.split(',') if isinstance(bbox,str) else bbox)
        require(-180<=w<e<=180 and -90<=s<n<=90,'invalid bbox')
        return start,end,[r for r in self.rows if start<=utc(r['time']).date()<=end and w<=r['longitude']<=e and s<=r['latitude']<=n]

    def field(self,start,end,bbox,limit=100,offset=0):
        require(type(limit) is int and 1<=limit<=10000 and type(offset) is int and offset>=0,'invalid pagination')
        _,_,rows=self._select(start,end,bbox)
        return dict(items=rows[offset:offset+limit],total=len(rows))

    def calendar(self,start,end,bbox):
        d,end,rows=self._select(start,end,bbox);groups=defaultdict(list)
        for r in rows:groups[utc(r['time']).date()].append(r)
        result=[]
        while d<=end:
            rr=groups[d];obs=sum(r['coverage_status']=='observed' for r in rr)
            result.append(dict(date=d.isoformat(),expected_active_cell_time_bins=sum(r['p_fire'] for r in rr) if rr else None,
                modeled_cell_time_bins=len(rr),observed_cell_time_bins=obs,coverage_status='observed' if obs else 'model_only' if rr else 'no_data'))
            d+=timedelta(days=1)
        return dict(items=result)


def main():
    p=argparse.ArgumentParser(description=__doc__);src=p.add_mutually_exclusive_group(required=True)
    src.add_argument('--run',type=Path,help='existing independent NASA run with --full');src.add_argument('--csv-dir',type=Path);src.add_argument('--raw-dir',type=Path);src.add_argument('--live',action='store_true')
    p.add_argument('--out',type=Path,default=ROOT/'model_preview'/'bc-july-2023');p.add_argument('--start',default='2023-07-01');p.add_argument('--end',default='2023-07-31');p.add_argument('--bbox',nargs=4,type=float,default=[-139,48,-114,60]);p.add_argument('--max-folds',type=int,default=4);p.add_argument('--particles',type=int,default=5000);p.add_argument('--login',default='interactive',choices=['interactive','netrc','environment','all']);p.add_argument('--install',action='store_true')
    a=p.parse_args()
    try:
        start,end=date.fromisoformat(a.start),date.fromisoformat(a.end);require(start<=end,'reversed dates');w,s,e,n=a.bbox;require(-180<=w<e<=180 and -90<=s<n<=90,'invalid bbox');require(not a.out.exists(),'output exists; choose --out new path');verify_algorithm()
        if a.install:subprocess.run([sys.executable,'-m','pip','install','-r',str(ALGO/('requirements-nasa.txt' if a.live or a.raw_dir else 'requirements.txt'))],check=True)
        run=a.run
        if run is None:
            parent=ROOT/'data'/'model_preview_runs';parent.mkdir(parents=True,exist_ok=True);batch=Path(tempfile.mkdtemp(prefix='preview_',dir=parent))
            cmd=[sys.executable,str(ALGO/'test_parsec_independent.py'),'nasa','--out-root',str(batch),'--full','--start',a.start,'--end',a.end,'--bbox',*map(str,a.bbox),'--max-folds',str(a.max_folds),'--particles',str(a.particles),'--login',a.login]
            cmd += ['--live'] if a.live else ['--csv-dir',str(a.csv_dir.resolve())] if a.csv_dir else ['--raw-dir',str(a.raw_dir.resolve())]
            rc=subprocess.run(cmd,check=False).returncode
            runs=[p for p in batch.iterdir() if (p/'NASA_REPORT.json').is_file()]
            require(len(runs)==1,f'NASA runner failed before report (exit {rc}); inspect {batch}')
            run=runs[0];print('NASA runner exit:',rc,'; inspecting eligible folds in',run)
        publish(run,a.out,start,end,a.bbox)
        return 0
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.CalledProcessError) as exc:
        print('ERROR:',exc,file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
