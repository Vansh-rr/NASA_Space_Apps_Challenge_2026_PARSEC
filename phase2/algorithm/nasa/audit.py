#!/usr/bin/env python3
"""Run existing PARSEC Level-2 bridge extractor on downloaded mask/geolocation pairs.
Reject synthetic fixtures by default; do NOT generate independent fire truth.
"""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
from .pilotlib import read_json, write_json, file_magic_ok, sha256


def run(plan,data_dir,out,bridge,bbox,allow_fixture=False):
    if not bridge.is_file():raise ValueError('Missing previous bridge extractor: '+str(bridge))
    out.mkdir(parents=True,exist_ok=True)
    summaries=[]
    for index,pair in enumerate(plan['pairs'],1):
        mask=pair['mask'];geo=pair['geo']
        mpath=data_dir/mask['filename'];gpath=data_dir/geo['filename']
        for p in (mpath,gpath):
            if not p.is_file():raise ValueError('Missing downloaded granule: '+str(p))
            if not file_magic_ok(p):raise ValueError('Not valid HDF/NetCDF science-format signature: '+str(p))
            if not allow_fixture and 'SYNTHETIC' in p.name.upper():
                raise ValueError('REFUSED synthetic fixture as authentic NASA granule')
            if not allow_fixture and p.suffix.lower() in ('.nc','.h5','.hdf5'):
                import h5py
                with h5py.File(p) as h:
                    if 'SYNTHETIC_FIXTURE_NOT_NASA' in h.attrs:
                        raise ValueError('REFUSED synthetic fixture marked by HDF5 attributes')
        sensor=pair['sensor'];product=mask['product'];collection=mask['collection_code']
        outfile=out/f'{sensor.lower()}_{pair["stamp"].replace(".","_")}_{index}.csv'
        args=[sys.executable,str(bridge),'--sensor',sensor,'--product',product,'--collection',collection,
              '--mask-file',str(mpath),'--geo-file',str(gpath), '--bbox',*[str(x) for x in bbox], '--out',str(outfile)]
        proc=subprocess.run(args,capture_output=True,text=True)
        print(proc.stdout,end='')
        if proc.stderr:print(proc.stderr,end='',file=sys.stderr)
        if proc.returncode:raise ValueError('Bridge extraction failed on '+mask['filename']+' (exit '+str(proc.returncode)+')')
        count=0;hist={str(i):0 for i in range(10)};usable=0;detected=0
        with outfile.open(newline='',encoding='utf-8') as f:
            for row in csv.DictReader(f):
                count+=1
                k=row['mask_class'];hist[k]+=1
                if row['usable']=='1':usable+=1
                if row['detected']=='1':detected+=1
                if row['granule_id']!=mask['filename'] or row['geolocation_granule_id']!=geo['filename']:
                    raise ValueError('Broken granule lineage in CSV')
                if k=='5' and (row['usable'],row['detected'])!=('1','0'):
                    raise ValueError('Negative mask semantics violated')
                if k in ('7','8','9') and (row['usable'],row['detected'])!=('1','1'):
                    raise ValueError('Positive mask semantics violated')
                if k in ('0','1','2','3','4','6') and (row['usable'],row['detected'])!=('0',''):
                    raise ValueError('Unavailable pixel improperly treated as non-fire')
        if count==0:
            raise ValueError('No pixels fall inside the study bbox for '+mask['filename']+'; try another granule or a correctly intersecting area')
        if usable==0:
            raise ValueError('No usable pixels in selected granule '+mask['filename']+'; choose another observation opportunity')
        summaries.append({'sensor':sensor,'mask':mask['filename'],'geolocation':geo['filename'],
                          'mask_sha256':sha256(mpath),'geo_sha256':sha256(gpath),
                          'output_csv':str(outfile),'pixels_in_bbox':count,'usable':usable,
                          'positive':detected,'negative':usable-detected,
                          'unavailable':count-usable,'classes':hist})
        print('AUDIT:',sensor,'pixels',count,'usable',usable,'detected',detected,'unavailable',count-usable)
    write_json(out/'pilot_audit.json',{'source_kind':'FORMAT_CHECKED_GRANULES_PROVENANCE_REQUIRES_RECEIPTS' if not allow_fixture else 'SYNTHETIC_TEST_ONLY',
              'bbox_wsen':bbox,'summaries':summaries,
              'scientific_status':'NOT CALIBRATED: independent reference fire labels and comparable FRP not supplied; no pixel-footprint pairing verified.'})
    return summaries


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',default='output/pair_plan.json')
    p.add_argument('--data-dir',default='data/raw_l2')
    p.add_argument('--out',default='output/real_pilot')
    p.add_argument('--bridge',default=str(Path(__file__).resolve().parent/'extract.py'))
    p.add_argument('--require-both-sensors',action='store_true')
    # Only for package unit tests; NEVER for a scientific run.
    p.add_argument('--allow-synthetic-fixture-for-tests',action='store_true')
    a=p.parse_args()
    try:
        plan=read_json(a.plan)
        if a.require_both_sensors and {q['sensor'] for q in plan['pairs']}!={'MODIS','VIIRS'}:
            raise ValueError('Pilot must include both MODIS and VIIRS, but pairing plan does not')
        run(plan,Path(a.data_dir),Path(a.out),Path(a.bridge),plan['bbox_wsen'],a.allow_synthetic_fixture_for_tests)
        print('PASS: extracted mask/coverage observations. NOT a calibrated V2.1 dataset.')
    except (ValueError,KeyError,OSError,ImportError) as e:
        print('ERROR:',e,file=sys.stderr);return 2
    return 0

if __name__=='__main__':sys.exit(main())
