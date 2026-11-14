"""Independent regression tests for the single C engine."""
import copy,csv,itertools,json,math,os,subprocess,tempfile,unittest
from pathlib import Path
# Optional dependency bootstrap before third-party imports.
import sys
if __name__ == '__main__' and '--install' in sys.argv:
    here=Path(__file__).resolve().parent
    req=here/('requirements-nasa.txt' if any(x in sys.argv for x in ('--live','--raw-dir')) else 'requirements.txt')
    subprocess.run([sys.executable,'-m','pip','install','-r',str(req)],check=True)
import numpy as np
from scipy.special import expit
from shapely.geometry import box,mapping
from pyproj import Transformer
from prepare import transform
from prepare import write_field,compiled,demo,evaluate,read_csv,nasa_mask

ROOT=Path(__file__).resolve().parent
BIN=Path(os.environ.get('PARSEC_BIN',ROOT/'parsec')).resolve()

def observation(ident,t,s,c,d,r,ix,w,hold=False,group=None):
    return dict(observation_id=ident,group_id=group or ident,time_index=t,sensor=s,usable=c,detected=d,frp_mw=r,indices=ix,weights=w,holdout=hold)

def tiny():
    return dict(source_kind='SYNTHETIC',cells=['a','b'],times=['t0','t1','t2'],levels_mw=[0.,5.,20.],edges=[(0,1)],observations=[observation('m0',0,'modis',1,1,15,[0,1],[1,.5]),observation('v0',0,'viirs',1,0,None,[0],[1]),observation('v1',1,'viirs',1,1,18,[1],[1]),observation('m2',2,'modis',1,0,None,[0,1],[1,1]),observation('held',1,'modis',1,1,None,[0,1],[.5,1],True),observation('cloud',2,'viirs',0,None,None,[1],[1])])

class Core(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def run_fit(self,data,name='fit',solver='exact',particles=3000,lag=3,params='illustrative',draws=16,fail=False):
        field=self.p/f'{name}.txt';write_field(field,data);out=self.p/name
        p=subprocess.run([str(BIN),'fit',str(field),str(params),str(out),solver,str(particles),str(draws),str(lag),'42'],capture_output=True,text=True)
        if fail:self.assertNotEqual(p.returncode,0,p.stdout);return p
        self.assertEqual(p.returncode,0,p.stderr);return out
    def probs(self,path):return np.array([float(r['probability']) for r in read_csv(path/'posterior_probabilities.csv')])
    def test_analytic_one_cell(self):
        d=dict(source_kind='SYNTHETIC',cells=['a'],times=['t0'],levels_mw=[0.,20.],edges=[],observations=[observation('m',0,'modis',1,0,None,[0],[1]),observation('v',0,'viirs',1,1,None,[0],[1])]);out=self.run_fit(d);qm=expit(-1.5+.5*math.log(20));qv=expit(-.8+.7*math.log(20));a=.2*(1-qm)*qv;b=.8*.99*.005;self.assertAlmostEqual(self.probs(out)[1],a/(a+b),10)
    def test_bruteforce_smoother(self):
        d=tiny();out=self.run_fit(d);levels=np.array(d['levels_mw']);states=np.array(list(itertools.product(levels,repeat=2)));K=len(states)
        def transition(x,y):
            ans=1.
            for g in range(2):
                active=x is not None and x[g]>0;p=.2 if x is None else expit(math.log(.2/.8)+2.4*active+.9*(x[1-g]>0));center=math.log(x[g]) if active else 3.;m=np.exp(-.5*((np.log(levels[1:])-center)/.8)**2);m/=m.sum();ans*=1-p if y[g]==0 else p*m[np.where(levels[1:]==y[g])[0][0]]
            return ans
        def detection(s,q):return (.01 if s=='modis' else .005) if q==0 else expit((-1.5 if s=='modis' else -.8)+(.5 if s=='modis' else .7)*math.log(q))
        def likelihood(x,t):
            z=1.
            for o in d['observations']:
                if o['time_index']!=t or not o['usable'] or o['holdout']:continue
                q=sum(x[g]*w for g,w in zip(o['indices'],o['weights']));p=detection(o['sensor'],q);z*=p if o['detected'] else 1-p
                if o['frp_mw']:
                    r=o['frp_mw'];mu=math.log(q) if q else 1.;sd=(.32 if o['sensor']=='modis' else .2) if q else .8;z*=math.exp(-.5*((math.log(r)-mu)/sd)**2)/(r*sd*math.sqrt(2*math.pi))
            return z
        marginal=np.zeros((3,2,3));hold=0.;total=0.
        for ix in itertools.product(range(K),repeat=3):
            xs=states[list(ix)];w=transition(None,xs[0])*likelihood(xs[0],0)
            for t in (1,2):w*=transition(xs[t-1],xs[t])*likelihood(xs[t],t)
            total+=w;hold+=w*detection('modis',.5*xs[1,0]+xs[1,1])
            for t,g in itertools.product(range(3),range(2)):marginal[t,g,np.where(levels==xs[t,g])[0][0]]+=w
        np.testing.assert_allclose(self.probs(out),marginal.ravel()/total,atol=2e-10);self.assertAlmostEqual(float(read_csv(out/'holdout_predictions.csv')[0]['predicted_detection']),hold/total,10)
    def test_unavailable_and_holdout_no_leakage(self):
        d=tiny();a=self.run_fit(d,'a');d['observations']=[o for o in d['observations'] if o['usable']];next(o for o in d['observations'] if o['holdout'])['detected']=0;b=self.run_fit(d,'b');np.testing.assert_array_equal(self.probs(a),self.probs(b))
    def test_particle_matches_exact(self):
        a=self.run_fit(tiny(),'exact');b=self.run_fit(tiny(),'particle','particle',20000,2);self.assertLess(np.max(abs(self.probs(a)-self.probs(b))),.035);self.assertFalse(json.loads((b/'report.json').read_text())['warning'])
    def test_invalid_and_real_guard(self):
        d=tiny();d['observations'][0]['frp_mw']=0;self.run_fit(d,'zero',fail=True)
        d=tiny();d['source_kind']='REAL_REVIEWED';self.run_fit(d,'real',fail=True)
        d=tiny();d['observations'][0]['weights']=[2,.5];self.run_fit(d,'weight',fail=True)
        d=tiny();d['observations'][0]['usable']=0;self.run_fit(d,'unavailable',fail=True)
        d=tiny();d['source_kind']='NASA_MASK_EXPLORATORY';self.run_fit(d,'mask_frp',fail=True)
        d=tiny();d['observations'][1]['observation_id']='m0';self.run_fit(d,'dup',fail=True)
    def test_geometry(self):
        b=Transformer.from_crs(6933,4326,always_xy=True).transform;geom=lambda x:mapping(transform(b,x));bundle=dict(source_kind='SYNTHETIC',area_crs='EPSG:6933',start_utc='2023-07-01T00:00:00Z',bin_seconds=3600,n_bins=1,levels_mw=[0,20],cells=[dict(cell_id='a',geometry=geom(box(0,0,1000,1000))),dict(cell_id='b',geometry=geom(box(1000,0,2000,1000)))],observations=[dict(observation_id='o',group_id='o',sensor='modis',geometry=geom(box(0,0,1500,1000)),acquisition_utc='2023-07-01T00:00:00Z',usable=1,detected=1,frp_mw=15)])
        d,_=compiled(bundle);np.testing.assert_allclose(d['observations'][0]['weights'],[1,.5],atol=1e-7)
        d=copy.deepcopy(bundle);d['observations'][0]['geometry']=geom(box(0,0,2500,1000));self.assertRaises(ValueError,compiled,d)
    def test_nasa_mask_fixture_handoff(self):
        # Fabricated pixel CSVs, explicitly named TEST_ONLY. NOT live NASA data.
        from types import SimpleNamespace
        from prepare import nasa_auto,write_csv
        paths=[]
        for i,(sensor,product,time) in enumerate([('MODIS','MOD14','2023-07-01T12:00:00Z'),('VIIRS','VNP14IMG','2023-07-01T12:15:00Z'),('VIIRS','VNP14IMG','2023-07-01T13:00:00Z')]):
            g=f'TEST_ONLY_{product}_{i}';rows=[]
            for line in range(12):
                for sample in range(12):
                    m=7 if (line+sample)%7==0 else 2 if (line+sample)%11==0 else 5
                    rows.append(dict(sensor=sensor,product=product,collection='fixture',granule_id=g,geolocation_granule_id=g+'_geo',time_utc=time,latitude=53.001+line*.003,longitude=-122.039+sample*.003,line=line,sample=sample,mask_class=m,usable=int(m in (5,7)),detected=1 if m==7 else 0 if m==5 else '',pixel_stride=1))
            p=self.p/f'fixture{i}.csv';write_csv(p,rows);paths.append(p)
        target=self.p/'nasa_input';nasa_auto(SimpleNamespace(csv=paths,holdout=None,tile_deg=.02,cell_m=3000,bin_seconds=3600,out=target));report=json.loads((target/'report.json').read_text());self.assertEqual(report['source_kind'],'NASA_MASK_EXPLORATORY');self.assertEqual(report['heldout_granules'],['TEST_ONLY_VNP14IMG_2'])
        out=self.p/'nasa_fit';p=subprocess.run([str(BIN),'fit',str(target/'field.txt'),'illustrative',str(out),'auto','3000','1','3','42'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
        metrics=read_csv(out/'holdout_metrics.csv');self.assertEqual(metrics[0]['sensor'],'VIIRS');self.assertGreater(int(metrics[0]['n']),0)
        fit=json.loads((out/'report.json').read_text());self.assertEqual(fit['source_kind'],'NASA_MASK_EXPLORATORY');self.assertGreater(fit['train_modis'],0);self.assertGreater(fit['train_viirs'],0)
    def test_calibration_and_mixture(self):
        demo(self.p/'demo');d=self.p/'demo';cal=self.p/'cal';p=subprocess.run([str(BIN),'calibrate',str(d/'pairs.txt'),str(d/'labels.txt'),str(cal),'700','1200','42'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
        rows=read_csv(cal/'calibration_summary.csv');truth=json.loads((d/'truth_parameters.json').read_text());self.assertEqual(len(rows),11)
        for row in rows:self.assertEqual(row['status'],'OK');self.assertLessEqual(float(row['ci95_low']),truth[row['parameter']]);self.assertGreaterEqual(float(row['ci95_high']),truth[row['parameter']])
        data=json.loads((d/'field.json').read_text());a=self.run_fit(data,'ensemble',params=cal/'params.txt');b=self.run_fit(data,'repeat',params=cal/'params.txt');np.testing.assert_array_equal(self.probs(a),self.probs(b))
        post=self.probs(a).reshape(-1,4);x=np.array(data['levels_mw']);var=post@(x*x)-(post@x)**2
        rows=read_csv(a/'field_posterior.csv');np.testing.assert_allclose(var,[float(r['within_variance_mw2'])+float(r['between_variance_mw2']) for r in rows],atol=1e-7)
        evaluate(a,d/'reference.csv',d/'protocol.json',self.p/'eval');v=json.loads((self.p/'eval/validation_report.json').read_text());self.assertLess(v['model']['rmse_mw'],v['baseline']['rmse_mw']);self.assertLess(v['model']['brier'],v['baseline']['brier'])
        ref=read_csv(d/'reference.csv');ref[0]['group_id']='cal_pair_0';from prepare import write_csv;write_csv(self.p/'leak.csv',ref);self.assertRaises(ValueError,evaluate,a,self.p/'leak.csv',d/'protocol.json',self.p/'leak')


# Standalone runner. No imports from repository test suites or Phase 2.
import argparse, sys, hashlib, re
from datetime import datetime, timezone
from types import SimpleNamespace
from prepare import nasa_auto, project_geojson, write_csv, dump, utc
from shapely.strtree import STRtree


def command(args, log=None):
    args=[str(x) for x in args];print('+', ' '.join(args),flush=True)
    if log is None:subprocess.run(args,cwd=ROOT,check=True)
    else:
        with Path(log).open('w') as f:result=subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,text=True)
        if result.returncode:
            print(Path(log).read_text()[-4000:],file=sys.stderr)
            raise RuntimeError(f'command failed ({result.returncode}); see {log}')


def fresh(root):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_'),dir=root))


def build(run):
    global BIN
    BIN=(run/'parsec').resolve()
    command(['gcc','-std=c11','-O3','-Wall','-Wextra','-Wpedantic','-Werror',ROOT/'parsec.c','-lm','-o',BIN])


def fit_file(field,out,particles=5000,params='illustrative',draws=1,reviewed=False):
    args=[BIN,'fit',field,params,out,'auto',particles,draws,3,42]
    if reviewed:args.append('reviewed')
    command(args,Path(out).with_suffix('.log'))
    return json.loads((Path(out)/'report.json').read_text())


def metrics(y,p):
    from scipy.stats import rankdata
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    if len(y)==0 or y.shape!=p.shape or not np.isfinite(p).all() or np.any((p<0)|(p>1)) or np.any((y!=0)&(y!=1)):raise ValueError('invalid/empty predictive comparison')
    q=np.clip(p,1e-15,1-1e-15);pos=int(y.sum());neg=int(len(y)-pos);a=None
    if pos and neg:a=float((rankdata(p)[y==1].sum()-pos*(pos+1)/2)/(pos*neg))
    return dict(n=len(y),positives=pos,negatives=neg,brier=float(np.mean((p-y)**2)),logloss=float(-np.mean(y*np.log(q)+(1-y)*np.log1p(-q))),mean_probability=float(p.mean()),observed_rate=float(y.mean()),auc=a)


def raw_overlap(bundle,data):
    """Overlap-weighted raw detections in same nominal time bin; not truth.
    Overlapping footprints may repeat area. No extrapolation outside support.
    """
    obs=data['observations'];geoms={o['observation_id']:project_geojson(o['geometry'],bundle['area_crs']) for o in bundle['observations']};groups={}
    for o in obs:
        if o['usable'] and not o['holdout']:groups.setdefault((o['sensor'],o['time_index']),[]).append(o)
    indexed={k:(v,STRtree([geoms[o['observation_id']] for o in v])) for k,v in groups.items()};result={}
    for o in obs:
        if not o['usable'] or not o['holdout']:continue
        g=geoms[o['observation_id']];row={}
        for sensor in ('modis','viirs'):
            entry=indexed.get((sensor,o['time_index']));den=num=0.
            if entry:
                candidates,tree=entry
                for j in tree.query(g,predicate='intersects'):
                    r=candidates[int(j)];area=g.intersection(geoms[r['observation_id']]).area;den+=area;num+=area*r['detected']
            row[sensor]=min(1.,max(0.,num/den)) if den>1e-5 else None
        result[o['observation_id']]=row
    return result


def comparison(input_dir,work,particles=5000):
    """Identical held-out observations for every method; never train on test labels."""
    bundle=json.loads((input_dir/'bundle.json').read_text());data,_=compiled(bundle,exploratory=True);obs=data['observations']
    train={s for s in ('modis','viirs') if any(o['sensor']==s and o['usable'] and not o['holdout'] for o in obs)}
    reports={};pred={};methods={'all_available':None}
    if len(train)==2:methods.update(modis_only='modis',viirs_only='viirs')
    for name,sensor in methods.items():
        field=input_dir/'field.txt'
        if sensor:
            field=work/f'{name}.txt';write_field(field,dict(data,observations=[o for o in obs if o['holdout'] or o['sensor']==sensor]))
        reports[name]=fit_file(field,work/name,particles)
        pred[name]={r['observation_id']:r for r in read_csv(work/name/'holdout_predictions.csv')}
    anchor=pred['all_available'];ids=set(anchor)
    if not ids:raise ValueError('empty holdout predictions')
    for name,p in pred.items():
        if set(p)!=ids or any(p[i]['detected']!=anchor[i]['detected'] for i in ids):raise ValueError('holdout mismatch between methods')
    raw=raw_overlap(bundle,data);rows=[]
    for ident,a in sorted(anchor.items()):
        row=dict(observation_id=ident,granule=a['group_id'],time=a['time'],target_sensor=a['sensor'],detected=int(a['detected']),constant_train=float(a['baseline_detection']))
        for name,p in pred.items():row[name]=float(p[ident]['predicted_detection'])
        row.update(raw_modis=raw[ident]['modis'],raw_viirs=raw[ident]['viirs']);rows.append(row)
    write_csv(work/'comparison_predictions.csv',rows);scores=[]
    def score(subset,models,stratum):
        if not subset:return
        y=[r['detected'] for r in subset];base=metrics(y,[r['constant_train'] for r in subset])['brier']
        for name in models:
            m=metrics(y,[r[name] for r in subset]);m.update(method=name,stratum=stratum,brier_skill_vs_constant=1-m['brier']/base if base>0 else None,numerical_warning=reports[name]['warning'] if name in reports else None)
            for alt in ('modis_only','viirs_only','raw_modis','raw_viirs'):
                bs=metrics(y,[r[alt] for r in subset])['brier'] if alt in models else None
                m['brier_skill_vs_'+alt]=1-m['brier']/bs if bs is not None and bs>0 else None
            scores.append(m)
    models=['constant_train',*methods];score(rows,models,'all_holdout')
    for sensor in ('modis','viirs'):
        rawname='raw_'+sensor;score([r for r in rows if r[rawname] is not None],models+[rawname],f'same_bin_overlap_{sensor}')
    both=[r for r in rows if r['raw_modis'] is not None and r['raw_viirs'] is not None];score(both,models+['raw_modis','raw_viirs'],'same_bin_overlap_both')
    write_csv(work/'comparison_metrics.csv',scores)
    out=dict(source_kind='NASA_MASK_EXPLORATORY',training_sensor_families=sorted(train),actual_fusion=len(train)==2,heldout_granules=sorted({r['granule'] for r in rows}),n=len(rows),positives=sum(r['detected'] for r in rows),negatives=sum(1-r['detected'] for r in rows),same_bin_both=len(both),numerical_warning=any(r['warning'] for r in reports.values()),scores=scores,solver_reports=reports,interpretation='Predictive agreement with withheld mask labels only; retrospective smoothing, nominal times, approximate footprints, illustrative parameters. No physical FRP accuracy or proof of superiority.')
    dump(work/'comparison_report.json',out);return out


REQUIRED_COLUMNS=set('sensor product collection granule_id geolocation_granule_id time_utc latitude longitude line sample mask_class usable detected pixel_stride'.split())
NASA_NAME=re.compile(r'^(MOD14|MYD14|VNP14IMG|VJ114IMG|VJ214IMG)\.A\d{7}\.\d{4}\.\d{3}\.\d{13}\.(hdf|nc)$')


def discover(folder):
    folder=Path(folder).resolve();paths=[];groups={}
    for p in sorted(folder.glob('*.csv')):
        with p.open(newline='') as f:
            reader=csv.DictReader(f)
            if not REQUIRED_COLUMNS.issubset(reader.fieldnames or []):continue
            local={};checked={}
            for r in reader:
                g=r['granule_id'];match=NASA_NAME.fullmatch(g)
                if not match or match[1]!=r['product']:raise ValueError(f'{p.name}: not a recognized NASA fire-mask filename: {g}')
                expected='modis' if match[1] in ('MOD14','MYD14') else 'viirs'
                if r['sensor'].lower()!=expected:raise ValueError(f'{p.name}: sensor/product mismatch')
                key=(g,r['time_utc'])
                if key not in checked:
                    t=utc(r['time_utc']);acq=datetime.strptime(g.split('.')[1][1:]+g.split('.')[2],'%Y%j%H%M').replace(tzinfo=timezone.utc)
                    if t!=acq:raise ValueError(f'{p.name}: nominal timestamp mismatch')
                    checked[key]=t.isoformat()
                if r['pixel_stride']!='1':raise ValueError(f'{p.name}: stride must be 1')
                local[g]=(expected,checked[key])
            if not local:continue
            duplicate=set(local)&set(groups)
            if duplicate:raise ValueError(f'duplicate granule across CSVs: {sorted(duplicate)}; use one extraction per granule')
            groups.update(local);paths.append(p)
    if not paths or {s for s,t in groups.values()}!={'modis','viirs'}:raise ValueError(f'No valid extracted CSV set containing both sensors in {folder}. Use --raw-dir or --live if CSVs are missing.')
    return paths,groups


def nasa_run(args,run):
    if args.live or args.raw_dir:
        if not (ROOT/'nasa/acquire.py').is_file():raise ValueError('Optional NASA acquisition files missing; install nasa/ files or use --csv-dir')
        out=run/'acquisition'
        if args.live:cmd=[sys.executable,'-m','nasa.acquire','live','--start',args.start,'--end',args.end,'--bbox',*args.bbox,'--per-sensor',args.per_sensor,'--limit',300,'--login',args.login,'--out',out]
        else:
            raw=Path(args.raw_dir).resolve();files=sorted([*raw.glob('*.hdf'),*raw.glob('*.nc')]);cmd=[sys.executable,'-m','nasa.acquire','local',*files,'--bbox',*args.bbox,'--out',out]
        command(cmd);folder=out/'extracted'
    else:folder=args.csv_dir or ROOT/'output/nasa/extracted'
    paths,groups=discover(folder);dump(run/'input_granules.json',dict(csv_paths=[str(p) for p in paths],granules=groups,provenance='User-supplied or locally acquired mask CSVs; lineage format checked, not independently authenticated.'))
    order={s:sorted((g for g,(ss,t) in groups.items() if ss==s),key=lambda g:(groups[g][1],g)) for s in ('viirs','modis')};folds=[]
    for i in range(max(map(len,order.values()))):
        for s in ('viirs','modis'):
            if i<len(order[s]):folds.append(order[s][i])
    if args.holdout:
        if args.holdout not in groups:raise ValueError('requested holdout not present in extracted CSVs')
        folds=[args.holdout]
    folds=folds[:args.max_folds];dump(run/'fold_plan.json',dict(heldout_granules=folds,selection='predeclared acquisition order; coverage-only tile selection'));results=[];all_scores=[]
    for i,g in enumerate(folds,1):
        work=run/f'fold_{i:02d}';work.mkdir();inp=work/'input';print(f'\n--- Fold {i}/{len(folds)}: {g} ---',flush=True)
        try:nasa_auto(SimpleNamespace(csv=paths,holdout=[g],tile_deg=args.tile_deg,cell_m=args.cell_m,bin_seconds=args.bin_seconds,out=inp))
        except ValueError as e:
            results.append(dict(granule=g,status='NO_ELIGIBLE_GEOMETRY',reason=str(e)));print('SKIPPED:',e);continue
        try:
            r=comparison(inp,work,args.particles);status='NUMERICAL_WARNING' if r['numerical_warning'] else 'COMPLETED_ONE_CLASS' if not r['positives'] or not r['negatives'] else 'COMPLETED_TWO_CLASSES'
            if args.full:
                full=fit_file(inp/'field_all.txt',work/'full_reconstruction',args.particles);dump(work/'full_status.json',full)
            results.append(dict(granule=g,status=status,actual_fusion=r['actual_fusion'],n=r['n'],positives=r['positives'],negatives=r['negatives'],same_bin_both=r['same_bin_both'],path=str(work)))
            for row in r['scores']:all_scores.append(dict(fold=i,granule=g,status=status,**row))
        except (ValueError,RuntimeError,subprocess.CalledProcessError) as e:
            results.append(dict(granule=g,status='EXECUTION_FAILED',reason=str(e)));print('FAILED:',e)
    if all_scores:write_csv(run/'nasa_comparison_metrics.csv',all_scores)
    good=[r for r in results if r['status']=='COMPLETED_TWO_CLASSES'];done=[r for r in results if r['status'].startswith('COMPLETED')];status='NO_RELIABLE_FOLDS' if not done else 'EXECUTION_ONLY_NO_TWO_CLASS_FOLD' if not good else 'EXPLORATORY_PREDICTIVE_EVIDENCE'
    if any(r['status']=='EXECUTION_FAILED' for r in results):status='PARTIAL_EXECUTION_FAILURE'
    summary=dict(status=status,attempted=len(folds),completed_without_warning=len(done),two_class_folds=len(good),two_class_fusion_folds=sum(r['actual_fusion'] for r in good),folds=results,physical_accuracy='NOT MEASURED; independent reference data and calibrated retrieval support required',limitations='Overlapping granules/events may be correlated; scores descriptive per-fold. No selection on holdout detections; one-class folds cannot establish discrimination.')
    dump(run/'NASA_REPORT.json',summary);print(json.dumps(summary,indent=2));print('Reports:',run)
    return 0 if done and not any(r['status']=='EXECUTION_FAILED' for r in results) else 2


def offline_run(run):
    suite=unittest.TestSuite();suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(Core));suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
    with (run/'offline_tests.log').open('w') as f:result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
    print((run/'offline_tests.log').read_text());dump(run/'offline_status.json',dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful()))
    if not result.wasSuccessful():return 2
    d=run/'synthetic_input';demo(d);cal=run/'calibration';command([BIN,'calibrate',d/'pairs.txt',d/'labels.txt',cal,700,1200,42],run/'calibration.log');fit_file(d/'field.txt',run/'synthetic_fit',params=cal/'params.txt',draws=16);evaluate(run/'synthetic_fit',d/'reference.csv',d/'protocol.json',run/'synthetic_validation')
    demo(run/'stress_input',42,20,8);stress=fit_file(run/'stress_input/field.txt',run/'stress_fit',3000)
    dump(run/'stress_status.json',dict(executed=True,numerical_warning=stress['warning'],interpretation='Stress execution is not a stability pass; do not hide low ESS or ancestry warnings.'))
    print('PASS: independent offline suite and synthetic calibration-to-validation workflow. Stress warning:',stress['warning'],'Reports:',run);return 0


class Independent(unittest.TestCase):
    def test_missing_csv_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'No valid extracted CSV'):discover(tmp)
    def test_metrics_one_class(self):
        self.assertIsNone(metrics([0,0],[.1,.2])['auc']);self.assertAlmostEqual(metrics([0,1],[.1,.9])['auc'],1.)
    def test_same_holdout_comparators(self):
        # Explicitly fabricated masks: NEVER exported as NASA evidence.
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);paths=[]
            for k,(sensor,product) in enumerate([('MODIS','MOD14'),('VIIRS','VNP14IMG'),('VIIRS','VNP14IMG')]):
                g=f'TEST_ONLY_{product}_{k}';rows=[]
                for line in range(12):
                    for sample in range(12):
                        m=7 if (line+sample+k)%7==0 else 5
                        rows.append(dict(sensor=sensor,product=product,collection='fixture',granule_id=g,geolocation_granule_id=g+'_geo',time_utc='2023-07-01T12:00:00Z',latitude=53.001+line*.003,longitude=-122.039+sample*.003,line=line,sample=sample,mask_class=m,usable=1,detected=int(m==7),pixel_stride=1))
                path=p/f'fixture{k}.csv';write_csv(path,rows);paths.append(path)
            with self.assertRaises(ValueError):discover(p)
            inp=p/'input';nasa_auto(SimpleNamespace(csv=paths,holdout=['TEST_ONLY_VNP14IMG_2'],tile_deg=.02,cell_m=3000,bin_seconds=3600,out=inp));self.assertTrue((inp/'field.txt').exists());result=comparison(inp,p,3000);self.assertTrue(result['actual_fusion']);self.assertGreater(result['same_bin_both'],0);self.assertGreater(result['n'],0)
            rows=read_csv(p/'comparison_predictions.csv');self.assertEqual(len(rows),result['n']);self.assertTrue(all(r['modis_only'] and r['viirs_only'] for r in rows))
            with self.assertRaisesRegex(ValueError,'already exists'):nasa_auto(SimpleNamespace(csv=paths,holdout=None,tile_deg=.02,cell_m=3000,bin_seconds=3600,out=inp))
            target=p/'opposite';nasa_auto(SimpleNamespace(csv=paths,holdout=['TEST_ONLY_MOD14_0'],tile_deg=.02,cell_m=3000,bin_seconds=3600,out=target));self.assertEqual(json.loads((target/'report.json').read_text())['training_sensor_families'],['viirs'])


def reviewed_run(args,run):
    data=Path(args.data_dir).resolve();needed=['reviewed_pairs.csv','reference_calibration.csv','calibration_protocol.json','reviewed_bundle.json','independent_holdout.csv','validation_protocol.json'];absent=[x for x in needed if not (data/x).is_file()]
    if absent:raise ValueError('Missing independently reviewed inputs: '+', '.join(absent)+'; see REAL_DATA_CONTRACT.md')
    ci=run/'cal_input';cal=run/'calibration';geom=run/'geometry';fit=run/'fit'
    command([sys.executable,ROOT/'prepare.py','calibration-input','--pairs',data/needed[0],'--labels',data/needed[1],'--protocol',data/needed[2],'--out',ci]);command([BIN,'calibrate',ci/'pairs.txt',ci/'labels.txt',cal,1500,2000,42,'reviewed'],run/'calibration.log');command([sys.executable,ROOT/'prepare.py','geometry','--bundle',data/needed[3],'--out',geom]);r=fit_file(geom/'field.txt',fit,args.particles,cal/'params.txt',32,True)
    if r['warning']:raise ValueError('numerical warning: do not claim validated physical accuracy')
    evaluate(fit,data/needed[4],data/needed[5],run/'validation',cal/'params.txt');print('Reviewed reference comparison:',run/'validation/validation_report.json');return 0


def main():
    p=argparse.ArgumentParser(description='Independent PARSEC algorithm test runner (no Phase 2 dependencies).');p.add_argument('stage',choices=['offline','nasa','reviewed','all']);p.add_argument('--out-root',default=str(ROOT/'algorithm_test_output'));p.add_argument('--install',action='store_true',help='Install requirements in active Python environment before running')
    a=p.add_mutually_exclusive_group();a.add_argument('--csv-dir');a.add_argument('--raw-dir');a.add_argument('--live',action='store_true');p.add_argument('--start',default='2023-07-01');p.add_argument('--end',default='2023-07-08');p.add_argument('--bbox',nargs=4,type=float,default=[-139,48,-114,60]);p.add_argument('--per-sensor',type=int,choices=[1,2],default=2);p.add_argument('--login',choices=['interactive','all','netrc','environment'],default='interactive');p.add_argument('--max-folds',type=int,default=4);p.add_argument('--holdout');p.add_argument('--tile-deg',type=float,default=.02);p.add_argument('--cell-m',type=float,default=2500);p.add_argument('--bin-seconds',type=int,default=3600);p.add_argument('--particles',type=int,default=5000);p.add_argument('--full',action='store_true');p.add_argument('--data-dir',default='data');args=p.parse_args();run=fresh(args.out_root);print('RUN DIRECTORY:',run,flush=True)
    try:
        if not 1<=args.max_folds<=100 or not 100<=args.particles<=100000:raise ValueError('invalid fold/particle limit')
        build(run);dump(run/'run_metadata.json',dict(stage=args.stage,source_sha256=hashlib.sha256((ROOT/'parsec.c').read_bytes()).hexdigest(),prepare_sha256=hashlib.sha256((ROOT/'prepare.py').read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),python=sys.version,seed=42))
        if args.stage in ('offline','all'):
            rc=offline_run(run)
            if rc:return rc
        if args.stage in ('nasa','all'):return nasa_run(args,run)
        if args.stage=='reviewed':return reviewed_run(args,run)
        return 0
    except (OSError,ValueError,RuntimeError,KeyError,subprocess.CalledProcessError) as e:
        dump(run/'ERROR.json',dict(error=str(e)));print('ERROR:',e,'\nReports:',run,file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())

