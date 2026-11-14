"""PARSEC geometry, input preparation and evaluation. Inference lives in parsec.c."""
from datetime import datetime, timezone, timedelta
import math
import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping, Polygon
from shapely import transform as _shapely_transform
from shapely.strtree import STRtree
from scipy.sparse import csr_matrix


def transform(fn, geometry):
    """Shapely 2.x array API, compatible with 2.0 and 2.1+."""
    return _shapely_transform(geometry, lambda xy: np.column_stack(fn(xy[:, 0], xy[:, 1])))


def utc(x):
    t=datetime.fromisoformat(x.replace('Z','+00:00'))
    if t.tzinfo is None: raise ValueError('UTC offset required')
    return t.astimezone(timezone.utc)


def project_geojson(geom, crs):
    g=shape(geom)
    if g.geom_type not in ('Polygon','MultiPolygon') or g.is_empty or not g.is_valid: raise ValueError('invalid polygon')
    w,s,e,n=g.bounds
    if not (-180<=w<=e<=180 and -90<=s<=n<=90 and e-w<180): raise ValueError('invalid/antimeridian geometry')
    g=transform(Transformer.from_crs('EPSG:4326',crs,always_xy=True).transform,g)
    if not g.is_valid or not math.isfinite(g.area) or g.area<=0: raise ValueError('invalid projected area')
    return g


def compile_bundle(bundle, exploratory=False):
    """Contract: EPSG:4326 polygons, UTC regular bins, non-overlapping cells.
    Keep sparse weights; reject clipped footprints rather than pretending outside is zero.
    """
    kind=bundle['source_kind']; real=kind=='REAL_REVIEWED'
    if kind not in ('SYNTHETIC','REAL_REVIEWED') and not (exploratory and kind=='NASA_MASK_EXPLORATORY'): raise ValueError('source_kind must be SYNTHETIC or REAL_REVIEWED')
    if real and (not bundle.get('review_evidence') or 'truth_mw' in bundle): raise ValueError('real geometry requires review evidence and must not contain reference truth')
    crs=CRS.from_user_input(bundle['area_crs']); op=crs.coordinate_operation
    if not crs.is_projected or op is None or 'equal area' not in op.method_name.lower().replace('-',' '): raise ValueError('projected equal-area CRS required')
    if any(abs(ax.unit_conversion_factor-1)>1e-10 for ax in crs.axis_info): raise ValueError('metre CRS required')
    cells=bundle['cells']; names=[c['cell_id'] for c in cells]
    if not names or any(not x for x in names) or len(set(names))!=len(names): raise ValueError('unique cell IDs required')
    gs=[project_geojson(c['geometry'],crs) for c in cells]; tree=STRtree(gs); areas=np.array([g.area for g in gs]); ar=[]; ac=[]
    for i,g in enumerate(gs):
        for j in tree.query(g,predicate='intersects'):
            if j<=i: continue
            h=gs[j]; inter=g.intersection(h)
            if inter.area>max(1e-5,1e-9*min(g.area,h.area)): raise ValueError('overlapping grid cells')
            if g.boundary.intersection(h.boundary).length>1e-5: ar.extend([i,j]);ac.extend([j,i])
    adjacency=csr_matrix((np.ones(len(ar)),(ar,ac)),shape=(len(gs),len(gs)))
    start=utc(bundle['start_utc']); step=bundle['bin_seconds']; T=bundle['n_bins']
    if type(step) is not int or step<=0 or type(T) is not int or not 1<=T<=500: raise ValueError('invalid time grid')
    times=[(start+timedelta(seconds=t*step)).isoformat() for t in range(T)]
    rows=[]; audit=[]; seen=set()
    for o in bundle['observations']:
        ident=o['observation_id']
        if not ident or ident in seen: raise ValueError('duplicate/empty observation ID')
        seen.add(ident); sensor=o['sensor'].lower()
        if sensor not in ('modis','viirs'): raise ValueError('invalid sensor')
        c,d,r=o['usable'],o.get('detected'),o.get('frp_mw')
        if c not in (0,1) or (c==0 and (d is not None or r is not None)) or (c==1 and d not in (0,1)) or (r is not None and (d!=1 or not math.isfinite(r) or r<=0)): raise ValueError('invalid observation state')
        if real:
            if any(not o.get(k) for k in ('source_granule','footprint_evidence','geometry_quality','time_basis','product','satellite')): raise ValueError('missing real observation provenance')
            if o['geometry_quality'] not in ('reviewed_polygon','reviewed_approximate'): raise ValueError('unreviewed geometry')
            if o['time_basis']!='pixel_utc' and r is not None: raise ValueError('real FRP requires pixel acquisition time')
            if sensor=='viirs' and r is not None: raise ValueError('real VIIRS FRP disabled: 375/750 m retrieval support requires separate validated operator')
            if r is not None and not o.get('frp_support_evidence'): raise ValueError('real FRP support must be reviewed')
        t=math.floor((utc(o['acquisition_utc'])-start).total_seconds()/step)
        if not 0<=t<T: raise ValueError('observation outside time grid')
        g=project_geojson(o['geometry'],crs); idx=[]; weights=[]; covered=0.
        for j in sorted(tree.query(g,predicate='intersects')):
            a=g.intersection(gs[j]).area
            if a<=1e-9: continue
            idx.append(int(j));weights.append(min(1.,float(a/areas[j])));covered+=a
        frac=covered/g.area
        if not idx or not .99999<=frac<=1.00001: raise ValueError(f'footprint {ident} clipped/outside grid: coverage={frac:.6f}; expand grid')
        row={k:v for k,v in o.items() if k!='geometry'};row.update(time_index=t,indices=idx,weights=weights,sensor=sensor)
        rows.append(row);audit.append(dict(observation_id=ident,footprint_area_m2=g.area,covered_fraction=frac,cell_count=len(idx)))
    if not rows or not any(r['usable'] for r in rows): raise ValueError('no usable observations')
    return dict(source_kind=kind,cells=names,times=times,levels_mw=bundle['levels_mw'],adjacency=adjacency,observations=rows,**({'truth_mw':bundle['truth_mw']} if 'truth_mw' in bundle else {})),audit

import csv,math
from collections import Counter
from pathlib import Path
import numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon,mapping,box,Point



def build_candidates(paths,bbox,cell_m=1000,bin_seconds=3600,max_rows=300000,max_cells=100,max_candidates=10000):
    w,s,e,n=map(float,bbox)
    if not -180<=w<e<=180 or not -86<=s<n<=86 or e-w>.5 or n-s>.5:raise ValueError('candidate pilot requires a regional bbox no larger than 0.5x0.5 degrees, within +/-86 latitude')
    if not 100<=cell_m<=50000 or type(bin_seconds) is not int or bin_seconds<60:raise ValueError('invalid cell size or bin width')
    forward=Transformer.from_crs(4326,6933,always_xy=True);back=Transformer.from_crs(6933,4326,always_xy=True)
    obs=[]; stats=Counter(); seen=set(); bounds=[];times=[]
    for path in paths:
        rows={}
        with Path(path).open(newline='') as f:
            for r in csv.DictReader(f):
                lat=float(r['latitude']);lon=float(r['longitude'])
                if not (w-.1<=lon<=e+.1 and s-.1<=lat<=n+.1):continue
                if r['pixel_stride']!='1':raise ValueError('stride 1 required to recover neighborhoods')
                if 'SYNTHETIC' in r['granule_id'].upper():raise ValueError('synthetic fixture not allowed as real candidate')
                key=(r['granule_id'],int(r['line']),int(r['sample']))
                if key in rows:raise ValueError('duplicate pixel key')
                rows[key]=(r,np.array(forward.transform(lon,lat)))
                if len(rows)>max_rows:raise ValueError('too many ROI pixels; choose smaller bbox')
        for key,(r,center) in rows.items():
            lon=float(r['longitude']);lat=float(r['latitude'])
            if not (w<=lon<=e and s<=lat<=n):continue
            stats['roi_centers']+=1;g,i,j=key;sensor=r['sensor'].lower();scan=10 if sensor=='modis' else 32 if sensor=='viirs' else None
            if scan is None:raise ValueError('unsupported sensor')
            if i%scan in (0,scan-1) or j==0:stats['scan_boundary_skipped']+=1;continue
            neighbors=[(g,i+a,j+b) for a in (-1,0,1) for b in (-1,0,1)]
            if any(x not in rows for x in neighbors):stats['missing_neighbors_skipped']+=1;continue
            # Reject large/discontinuous neighborhoods (heuristic, not scientific QC).
            pts=np.array([rows[x][1] for x in neighbors]).reshape(3,3,2)
            spacing=np.r_[np.linalg.norm(np.diff(pts,axis=0),axis=-1).ravel(),np.linalg.norm(np.diff(pts,axis=1),axis=-1).ravel()]
            if not np.isfinite(pts).all() or spacing.min()<5 or spacing.max()>12000 or spacing.max()/spacing.min()>8:stats['irregular_neighborhood_skipped']+=1;continue
            corners=[pts[a:a+2,b:b+2].mean(axis=(0,1)) for a,b in ((0,0),(0,1),(1,1),(1,0))]; poly=Polygon(corners)
            if not poly.is_valid or poly.area<=0 or not poly.covers(Point(center)):stats['invalid_polygon_skipped']+=1;continue
            c=int(r['usable']);d=None if r['detected']=='' else int(r['detected']);m=int(r['mask_class']);
            if m not in range(10) or (c,d)!=((1,0) if m==5 else (1,1) if m in (7,8,9) else (0,None)):raise ValueError('inconsistent fire-mask semantics')
            ident=f'{g}:{i}:{j}'
            if ident in seen:raise ValueError('duplicate observation across CSVs')
            seen.add(ident);t=utc(r['time_utc']);times.append(t);bounds.append(poly.bounds)
            sat={'MOD14':'Terra','MYD14':'Aqua','VNP14IMG':'S-NPP','VJ114IMG':'NOAA-20','VJ214IMG':'NOAA-21'}.get(r['product'])
            if not sat:raise ValueError('unknown product')
            obs.append(dict(observation_id=ident,sensor=sensor,satellite=sat,product=r['product'],source_granule=g,geolocation_granule=r['geolocation_granule_id'],source_collection=r['collection'],acquisition_utc=t.isoformat(),time_basis='nominal_granule_utc',geometry_quality='candidate_unreviewed',footprint_evidence='3x3 neighboring centers; approximate; not native corners; REQUIRES REVIEW',geometry=mapping(transform(back.transform,poly)),usable=c,detected=d,frp_mw=None))
            stats['candidates']+=1;stats[sensor+'_candidates']+=1
            if len(obs)>max_candidates:raise ValueError('too many candidates; choose smaller bbox (no silent truncation)')
    if not obs:raise ValueError('no interior candidates in ROI; inspect audit CSVs and select another bbox')
    lo=np.min(np.array(bounds)[:,:2],axis=0);hi=np.max(np.array(bounds)[:,2:],axis=0);x0,y0=np.floor(lo/cell_m).astype(int);x1,y1=np.ceil(hi/cell_m).astype(int)
    if (x1-x0)*(y1-y0)>max_cells:raise ValueError('too many grid cells; reduce ROI or increase cell size')
    cells=[dict(cell_id=f'epsg6933_{cell_m:g}_{x}_{y}',geometry=mapping(transform(back.transform,box(x*cell_m,y*cell_m,(x+1)*cell_m,(y+1)*cell_m)))) for y in range(y0,y1) for x in range(x0,x1)]
    from datetime import datetime,timezone
    start=datetime.fromtimestamp(math.floor(min(t.timestamp() for t in times)/bin_seconds)*bin_seconds,timezone.utc);T=1+math.floor((max(times)-start).total_seconds()/bin_seconds)
    if T>500:raise ValueError('candidate time range too large')
    return dict(source_kind='CANDIDATE_UNREVIEWED',area_crs='EPSG:6933',start_utc=start.isoformat(),bin_seconds=bin_seconds,n_bins=T,cells=cells,observations=obs,levels_mw=[0,5,20,60],review_evidence='',calibration_evidence='',warning='Candidate geometry only. No native corners, true pixel times, FRP retrievals, or independent reference. Do not relabel without scientific review.'),dict(stats)

# Unified text contract; one C executable performs all numerical inference.
import argparse
import json
import re


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def safe_id(s):
    s=str(s)
    require(re.fullmatch(r'[A-Za-z0-9_.:+-]{1,190}',s),f'invalid identifier {s!r}')
    return s


def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def read_csv(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path,rows):
    require(rows,'empty table')
    with Path(path).open('w',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)


def write_field(path,data):
    cells,times,levels=data['cells'],data['times'],data['levels_mw']
    obs,edges=data['observations'],data['edges'];d=data.get('dynamics',{})
    roles={}
    with Path(path).open('w') as f:
        f.write(f"PARSEC_FIELD1 {data['source_kind']} {len(cells)} {len(times)} {len(levels)} {len(obs)} {len(edges)}\n")
        f.write(' '.join(map(str,levels))+'\n')
        f.write(' '.join(str(d.get(k,v)) for k,v in [('prior',.2),('persistence',2.4),('neighbor',.9),('mu',3.),('sd',.8)])+'\n')
        f.write(' '.join(map(safe_id,cells))+'\n'+' '.join(map(safe_id,times))+'\n')
        for i,j in edges:f.write(f'{i} {j}\n')
        for o in obs:
            group=safe_id(o['group_id']);hold=int(o.get('holdout',False))
            require(roles.setdefault(group,hold)==hold,'training/holdout group overlap')
            vals=[safe_id(o['observation_id']),group,o['time_index'],{'modis':0,'viirs':1}[o['sensor'].lower()],o['usable'],o['detected'] if o.get('detected') is not None else -1,o['frp_mw'] if o.get('frp_mw') is not None else -1,hold,len(o['indices'])]
            for i,w in sorted(zip(o['indices'],o['weights'])):vals.extend((i,format(w,'.17g')))
            f.write(' '.join(map(str,vals))+'\n')


def compiled(bundle,exploratory=False):
    data,audit=compile_bundle(bundle,exploratory=exploratory)
    ii,jj=data.pop('adjacency').nonzero();data['edges']=[(int(i),int(j)) for i,j in zip(ii,jj) if i<j]
    data['dynamics']=bundle.get('dynamics',{})
    for o in data['observations']:
        require(o.get('group_id'),'observation group_id required')
        if exploratory:require(o.get('frp_mw') is None,'NASA mask pilot must omit FRP')
    if bundle['source_kind']=='REAL_REVIEWED':require(bundle.get('calibration_evidence'),'calibration evidence required')
    return data,audit


def demo(out,seed=42,n=4,T=8):
    """Independent generator. Reference physical truth never enters C input."""
    require(2<=n<=30 and 2<=T<=30,'demo limits');out=Path(out);out.mkdir(parents=True,exist_ok=False);rng=np.random.default_rng(seed)
    with (out/'pairs.txt').open('w') as f:
        f.write('PAIRS1 SYNTHETIC 650\n')
        for i in range(650):
            h=rng.normal(3.4,.82);m=np.exp(h+.28+rng.normal(0,.32));v=np.exp(h+rng.normal(0,.2));f.write(f'cal_pair_{i//10} {m:.17g} {v:.17g}\n')
    truth_params=[(-1.5,.5,.01,.28,.32),(-.8,.7,.005,0.,.2)];sig=lambda x:1/(1+np.exp(-x));labels=[]
    for s,(alpha,beta,far,_,_) in enumerate(truth_params):
        for i in range(2500):
            z=int(rng.random()<.35);r=float(np.exp(rng.normal(3.2,1.2))) if z else 0.;c=int(rng.random()>.12);d=int(rng.random()<(sig(alpha+beta*math.log(r)) if z else far)) if c else -1
            labels.append(f'cal_ref_{i//10} {s} {z} {r:.17g} {c} {d}')
    (out/'labels.txt').write_text(f'LABELS1 SYNTHETIC {len(labels)}\n'+'\n'.join(labels)+'\n')
    levels=np.array([0.,5.,20.,60.]);logs=np.log(levels[1:]);obs=[];ref=[];prev=None
    for t in range(T):
        current=[]
        for i in range(n):
            nb=[j for j in (i-1,i+1) if 0<=j<n];active=0 if prev is None else int(prev[i]>0);p=.2 if prev is None else sig(math.log(.2/.8)+2.4*active+.9*np.mean([prev[j]>0 for j in nb]));center=math.log(prev[i]) if active else 3.;mass=np.exp(-.5*((logs-center)/.8)**2);mass/=mass.sum();current.append(float(rng.choice(levels,p=np.r_[1-p,p*mass])))
        prev=current
        for i,r in enumerate(current):ref.append(dict(time=f't{t}',cell_id=f'cell_{i}',group_id=f'eval_{t//2}',truth_fire=int(r>0),reference_frp_mw=r,baseline_fire_probability=.2,baseline_frp_mw=10))
        for s,(alpha,beta,far,bias,sd) in enumerate(truth_params):
            supports=[([i],[1.]) for i in range(n)] if s else [([i,i+1],[1.,.6]) for i in range(n-1)]
            for j,(ix,w) in enumerate(supports):
                q=sum(current[k]*v for k,v in zip(ix,w));c=int(rng.random()>.1);d=int(rng.random()<(sig(alpha+beta*math.log(q)) if q else far)) if c else None;r=float(np.exp(rng.normal(math.log(q)+bias if q else 1.,sd if q else .8))) if d and rng.random()>.1 else None
                obs.append(dict(observation_id=f'o_{t}_{s}_{j}',group_id=f'obs_{t}_{s}_{j}',time_index=t,sensor=['modis','viirs'][s],indices=ix,weights=w,usable=c,detected=d,frp_mw=r,holdout=s==1 and j==0))
    data=dict(source_kind='SYNTHETIC',cells=[f'cell_{i}' for i in range(n)],times=[f't{t}' for t in range(T)],levels_mw=levels.tolist(),edges=[(i,i+1) for i in range(n-1)],observations=obs)
    write_field(out/'field.txt',data);dump(out/'field.json',data);write_csv(out/'reference.csv',ref)
    dump(out/'truth_parameters.json',dict(mu=3.4,tau=.82,modis_bias=.28,modis_sd=.32,viirs_sd=.2,modis_alpha=-1.5,modis_beta=.5,modis_far=.01,viirs_alpha=-.8,viirs_beta=.7,viirs_far=.005))
    dump(out/'protocol.json',dict(source_kind='SYNTHETIC',calibration_groups=[f'cal_pair_{i}' for i in range(65)]+[f'cal_ref_{i}' for i in range(250)]));print('PASS: synthetic input and separate reference truth')


def nasa_mask(args):
    require(not Path(args.out).exists(), f"output already exists: {args.out}; select a new directory")
    # Candidate geometry is expressly exploratory, never reviewed/real-calibrated.
    bundle,stats=build_candidates(args.csv,args.bbox,cell_m=args.cell_m,bin_seconds=args.bin_seconds)
    bundle['source_kind']='NASA_MASK_EXPLORATORY';held=set(args.holdout)
    for o in bundle['observations']:
        o['group_id']=o['source_granule'];o['holdout']=o['group_id'] in held
    data,audit=compiled(bundle,exploratory=True)
    usable=[o for o in data['observations'] if o['usable']]
    require({o['sensor'] for o in usable}=={'modis','viirs'},'ROI must contain both usable sensors')
    train=[o for o in usable if not o['holdout']];test=[o for o in usable if o['holdout']]
    require(train and test and held=={o['group_id'] for o in test},'holdout granules must contain usable observations in ROI')
    require(len({o['sensor'] for o in test})==1, 'hold out one sensor family per experiment')
    require(args.holdout and any(o['sensor'] != test[0]['sensor'] for o in train), 'need other-sensor training coverage')
    support=lambda rr:{i for o in rr for i in o['indices']}
    shared=support(train)&support(test);require(shared,'no shared training/holdout cell support')
    require(support([o for o in train if o['sensor'] != test[0]['sensor']]) & support(test),'no shared opposite-sensor training/holdout cell support')
    require(support([o for o in usable if o['sensor']=='modis'])&support([o for o in usable if o['sensor']=='viirs']),'no shared MODIS/VIIRS grid support')
    import tempfile
    target=Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.preparing_',dir=target.parent) as tmp:
        out=Path(tmp)/'input';out.mkdir();write_field(out/'field.txt',data);dump(out/'bundle.json',bundle);write_csv(out/'footprint_audit.csv',audit)
        # Separate full-observation reconstruction; NEVER score it as holdout.
        full=dict(data,observations=[dict(o,holdout=False) for o in data['observations']]);write_field(out/'field_all.txt',full)
        counts=Counter((o['sensor'], 'holdout' if o['holdout'] else 'train',str(o['detected'])) for o in usable)
        dump(out/'report.json',dict(source_kind=bundle['source_kind'],counts={'_'.join(k):v for k,v in counts.items()},shared_train_holdout_cells=len(shared),cells=len(data['cells']),time_bins=len(data['times']),heldout_granules=sorted(held),candidate_stats=stats,warning='Approximate footprints and nominal granule times; fixed illustrative parameters. No FRP or physical reference truth.'))
        require(not target.exists(),f'output already exists: {target}')
        out.rename(target)
    print('PASS: exploratory NASA mask input; prediction agreement only')


def nasa_auto(args):
    """Select a small common swath tile using coordinates/availability only.
    Rank by common coverage, never withheld detection labels. Prefer both
    sensor families in training; with one pair each, explicitly cross-sensor.
    """
    from types import SimpleNamespace
    require(not Path(args.out).exists(), f'output already exists: {args.out}; select a new directory')
    require(.005<=args.tile_deg<=.05,'tile-deg must be .005..0.05')
    tile=args.tile_deg;counts={};meta={}
    # Each extracted CSV is a granule. Preserve its entire holdout group.
    for path in args.csv:
        with Path(path).open(newline='') as f:
            for r in csv.DictReader(f):
                g=r['granule_id'];meta[g]=(r['sensor'].lower(),r['time_utc'])
                if r['usable']!='1':continue
                x=math.floor(float(r['longitude'])/tile);y=math.floor(float(r['latitude'])/tile)
                key=(x,y);counts.setdefault(key,Counter())[g]+=1
    vg=sorted((g for g,(s,t) in meta.items() if s=='viirs'),key=lambda g:(meta[g][1],g))
    require(vg,'no VIIRS granule available');hold=set(args.holdout or [vg[-1]])
    require(hold<=set(meta),'unknown holdout granule; use exact IDs from inventory')
    train_mod={g for g,(s,t) in meta.items() if s=='modis' and g not in hold};train_v={g for g,(s,t) in meta.items() if s=='viirs' and g not in hold}
    held_sensors={meta[g][0] for g in hold}
    require(len(held_sensors)==1,'hold out one sensor family per experiment')
    target=next(iter(held_sensors));other=train_mod if target=='viirs' else train_v
    require(other,'at least one other-sensor training granule required')
    ranks=[]
    for (x,y),c in counts.items():
        m=sum(c[g] for g in train_mod);v=sum(c[g] for g in train_v);h=sum(c[g] for g in hold)
        opposite=m if target=='viirs' else v
        if opposite and h and all(c[g] for g in hold):
            # Prefer genuine fusion, then permit cross-sensor-only tests.
            ranks.append((int(bool(m and v)),min(m,v,h) if m and v else min(opposite,h),opposite+h,x,y))
    require(ranks,'no common usable tile across selected training and held-out swaths; obtain other granules')
    last=None
    for _,_,_,x,y in sorted(ranks,reverse=True)[:16]:
        bbox=[x*tile,y*tile,(x+1)*tile,(y+1)*tile]
        try:
            nasa_mask(SimpleNamespace(csv=args.csv,bbox=bbox,cell_m=args.cell_m,bin_seconds=args.bin_seconds,holdout=sorted(hold),out=args.out))
        except ValueError as e:
            last=str(e);print('Candidate tile rejected:',bbox,last);continue
        p=Path(args.out)/'report.json';report=json.loads(p.read_text());report.update(selection='usable geographic common tile; no detection labels used',selected_bbox=bbox,holdout_selection='explicit granule IDs or latest VIIRS nominal acquisition',training_sensor_families=sorted({k.split('_')[0] for k in report['counts'] if '_train_' in k}));dump(p,report)
        print('Selected ROI:',bbox,'; held-out granules:',sorted(hold));return
    raise ValueError('no valid footprint tile among 16 candidates: '+str(last))


def inventory(paths):
    for path in paths:
        groups={}
        with Path(path).open(newline='') as f:
            for r in csv.DictReader(f):
                g=r['granule_id'];la,lo=float(r['latitude']),float(r['longitude']);a=groups.setdefault(g,dict(sensor=r['sensor'],time=r['time_utc'],west=lo,east=lo,south=la,north=la,rows=0));a['west']=min(a['west'],lo);a['east']=max(a['east'],lo);a['south']=min(a['south'],la);a['north']=max(a['north'],la);a['rows']+=1
        for g,a in groups.items():print(g,json.dumps(a))
    print('Rectangles are only approximate swath extents; choose ROI and holdout before inspecting its fire labels.')


def evaluate(run,reference,protocol,out,params=None):
    run=Path(run);r=json.loads((run/'report.json').read_text());p=json.loads(Path(protocol).read_text());kind=r['source_kind'];require(kind in ('SYNTHETIC','REAL_REVIEWED') and p['source_kind']==kind,'physical reference validation requires matching reviewed or synthetic source; mask agreement is not truth');require(not r['warning'],'numerical warning: review solver before validation')
    groups=set(p['calibration_groups']);require(groups,'calibration groups required');require(set((run/'calibration_groups.txt').read_text().split())==groups,'protocol must match actual calibration groups used in fit')
    if kind=='REAL_REVIEWED':
        require(params and r['calibration_kind']=='REAL_REVIEWED' and all(p.get(k) for k in ('independence_evidence','support_evidence','evaluation_design_evidence','baseline_evidence')),'incomplete independent reference protocol')
        toks=Path(params).read_text().split();require(toks[:2]==['PARSEC_PARAMS1','REAL_REVIEWED'] and set(toks[4:4+int(toks[3])])==groups,'calibration group mismatch')
    predictions={(x['time'],x['cell_id']):x for x in read_csv(run/'field_posterior.csv')};seen=set();rows=[]
    for x in read_csv(reference):
        key=(x['time'],x['cell_id']);require(key not in seen and key in predictions,'duplicate or unmatched reference key');seen.add(key);require(x['group_id'] and x['group_id'] not in groups,'calibration/evaluation leakage')
        if kind=='REAL_REVIEWED':
            require(all(x.get(k) for k in ('reference_source','reference_support_evidence','reference_time_evidence')),'reference provenance missing');require(not re.search(r'\b(MODIS|VIIRS|FIRMS|MOD14|MYD14|VNP14IMG)\b',x['reference_source'],re.I),'target observations are not independent truth')
        z=int(x['truth_fire']);y=float(x['reference_frp_mw']);bp=float(x['baseline_fire_probability']);bf=float(x['baseline_frp_mw']);require(z in (0,1) and math.isfinite(y) and ((z and y>0) or (not z and y==0)) and 0<=bp<=1 and math.isfinite(bf) and bf>=0,'invalid reference or baseline')
        a=predictions[key];q=float(a['p_fire']);m=float(a['mean_frp_mw']);lo=float(a['ci95_low_mw']);hi=float(a['ci95_high_mw']);rows.append(dict(time=key[0],cell_id=key[1],group_id=x['group_id'],truth_fire=z,reference_frp_mw=y,p_fire=q,mean_frp_mw=m,baseline_fire_probability=bp,baseline_frp_mw=bf,ci95_covered=int(lo<=y<=hi),usable_observation_count=a['usable_observation_count']))
    require(rows,'empty evaluation');y=np.array([x['reference_frp_mw'] for x in rows]);z=np.array([x['truth_fire'] for x in rows]);m=np.array([x['mean_frp_mw'] for x in rows]);q=np.array([x['p_fire'] for x in rows]);bf=np.array([x['baseline_frp_mw'] for x in rows]);bp=np.array([x['baseline_fire_probability'] for x in rows])
    def metrics(m,q):
        q=np.clip(q,1e-15,1-1e-15);return dict(rmse_mw=float(np.sqrt(np.mean((m-y)**2))),mae_mw=float(np.mean(abs(m-y))),bias_mw=float(np.mean(m-y)),brier=float(np.mean((q-z)**2)),logloss=float(-np.mean(z*np.log(q)+(1-z)*np.log1p(-q))))
    report=dict(source_kind=kind,rows=len(rows),groups=len({x['group_id'] for x in rows}),positive=int(z.sum()),negative=int(len(z)-z.sum()),model=metrics(m,q),baseline=metrics(bf,bp),interval_coverage=float(np.mean([x['ci95_covered'] for x in rows])),warning='Conditional on reference quality, support and representativeness. Not automatic scientific certification.')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);write_csv(out/'validation_rows.csv',rows);dump(out/'validation_report.json',report);print(json.dumps(report,indent=2))


def calibration_input(args):
    p=json.loads(Path(args.protocol).read_text());require(p.get('source_kind')=='REAL_REVIEWED' and all(p.get(k) for k in ('review_evidence','reference_independence_evidence','frp_scale_evidence','support_time_evidence')),'review and compatible FRP scale evidence required');pairs=read_csv(args.pairs);labels=read_csv(args.labels);groups=set(p['calibration_groups']);require(len(pairs)>=30 and labels and {r['group_id'] for r in pairs+labels}==groups,'insufficient rows or group mismatch');out=Path(args.out);out.mkdir(parents=True,exist_ok=False);seen=set();lines=[]
    for r in pairs:
        require(r['pair_id'] not in seen and r.get('support_evidence'),'duplicate or unreviewed pair');seen.add(r['pair_id']);m,v=float(r['modis_frp_mw']),float(r['viirs_frp_mw']);require(math.isfinite(m) and math.isfinite(v) and min(m,v)>0,'invalid FRP');lines.append(f"{safe_id(r['group_id'])} {m:.17g} {v:.17g}")
    (out/'pairs.txt').write_text(f'PAIRS1 REAL_REVIEWED {len(lines)}\n'+'\n'.join(lines)+'\n');seen=set();lines=[]
    for r in labels:
        key=(r['reference_id'],r['sensor']);require(key not in seen and all(r.get(k) for k in ('reference_source','support_evidence','time_evidence')),'missing reference provenance or duplicate');seen.add(key);require(not re.search(r'\b(MODIS|VIIRS|FIRMS|MOD14|MYD14|VNP14IMG)\b',r['reference_source'],re.I),'target sensor cannot supply reference truth');s={'modis':0,'viirs':1}[r['sensor'].lower()];z=int(r['truth_fire']);frp=float(r['reference_frp_mw']);c=int(r['usable']);d=int(r['detected']) if r['detected'] else -1;require(z in (0,1) and math.isfinite(frp) and ((z and frp>0) or (not z and frp==0)) and c in (0,1) and (d in (0,1) if c else d==-1),'invalid reference or coverage');lines.append(f"{safe_id(r['group_id'])} {s} {z} {frp:.17g} {c} {d}")
    (out/'labels.txt').write_text(f'LABELS1 REAL_REVIEWED {len(lines)}\n'+'\n'.join(lines)+'\n');dump(out/'review_protocol.json',p);print('PASS: reviewed calibration contract; attestations require external verification')


def main():
    p=argparse.ArgumentParser(description=__doc__);sp=p.add_subparsers(dest='cmd',required=True)
    q=sp.add_parser('demo');q.add_argument('--out',required=True);q.add_argument('--seed',type=int,default=42);q.add_argument('--cells',type=int,default=4);q.add_argument('--times',type=int,default=8)
    q=sp.add_parser('geometry');q.add_argument('--bundle',required=True);q.add_argument('--out',required=True)
    q=sp.add_parser('inventory');q.add_argument('--csv',nargs='+',required=True)
    q=sp.add_parser('nasa-auto');q.add_argument('--csv',nargs='+',required=True);q.add_argument('--tile-deg',type=float,default=.02);q.add_argument('--cell-m',type=float,default=2500);q.add_argument('--bin-seconds',type=int,default=3600);q.add_argument('--holdout',nargs='+');q.add_argument('--out',required=True)
    q=sp.add_parser('nasa-mask');q.add_argument('--csv',nargs='+',required=True);q.add_argument('--bbox',nargs=4,type=float,required=True);q.add_argument('--cell-m',type=float,default=2000);q.add_argument('--bin-seconds',type=int,default=3600);q.add_argument('--holdout',nargs='+',required=True);q.add_argument('--out',required=True)
    q=sp.add_parser('evaluate');q.add_argument('--run',required=True);q.add_argument('--reference',required=True);q.add_argument('--protocol',required=True);q.add_argument('--params');q.add_argument('--out',required=True)
    q=sp.add_parser('calibration-input');q.add_argument('--pairs',required=True);q.add_argument('--labels',required=True);q.add_argument('--protocol',required=True);q.add_argument('--out',required=True)
    a=p.parse_args()
    if a.cmd=='demo':demo(a.out,a.seed,a.cells,a.times)
    elif a.cmd=='geometry':
        bundle=json.loads(Path(a.bundle).read_text());data,audit=compiled(bundle);out=Path(a.out);out.mkdir(parents=True,exist_ok=False);write_field(out/'field.txt',data);write_csv(out/'footprint_audit.csv',audit);dump(out/'bundle.json',bundle);print('PASS: footprint operators')
    elif a.cmd=='inventory':inventory(a.csv)
    elif a.cmd=='nasa-mask':nasa_mask(a)
    elif a.cmd=='nasa-auto':nasa_auto(a)
    elif a.cmd=='evaluate':evaluate(a.run,a.reference,a.protocol,a.out,a.params)
    else:calibration_input(a)


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError) as e:raise SystemExit(f'ERROR: {e}')

