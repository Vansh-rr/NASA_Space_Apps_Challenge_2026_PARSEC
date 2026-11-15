"""Independent preview integration tests. All inputs are TEMPORARY SIMULATED masks.
Never commit generated fixture data or treat fixture scores as NASA evidence.
"""
from datetime import date
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from phase2.model_preview import PreviewStore, publish, ROOT, sha, verify_algorithm

BBOX=[-139,48,-114,60]
START=date(2023,7,1);END=date(2023,7,31)


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from phase2.algorithm.prepare import write_csv
        cls.tmp=tempfile.TemporaryDirectory(prefix='SIMULATED_ONLY_preview_')
        cls.p=Path(cls.tmp.name); folder=cls.p/'fixture';folder.mkdir()
        # Simulated NASA-format identifiers exercise the local discovery path.
        # Authenticity is NOT inferred from these filenames or the runner label.
        for k,(sensor,product,geop,collection) in enumerate([
            ('MODIS','MOD14','MOD03','061'),('VIIRS','VNP14IMG','VNP03IMG','002'),('VIIRS','VNP14IMG','VNP03IMG','002')]):
            suffix=f'.A2023182.12{15*k:02d}.{collection}.2023183051234.'+('hdf' if sensor=='MODIS' else 'nc')
            rows=[]
            for line in range(12):
                for sample in range(12):
                    m=7 if (line+sample+k)%7==0 else 5
                    rows.append(dict(sensor=sensor,product=product,collection=collection,granule_id=product+suffix,
                        geolocation_granule_id=geop+suffix,time_utc=f'2023-07-01T12:{15*k:02d}:00Z',
                        latitude=53.001+line*.003,longitude=-122.039+sample*.003,line=line,sample=sample,
                        mask_class=m,usable=1,detected=int(m==7),pixel_stride=1))
            write_csv(folder/f'fixture{k}.csv',rows)
        cls.out=cls.p/'output'
        result=subprocess.run([sys.executable,str(ROOT/'phase2/algorithm/test_parsec_independent.py'),'nasa','--csv-dir',str(folder),'--out-root',str(cls.p/'runs'),'--full','--max-folds','1','--particles','3000'],cwd=ROOT,capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
        cls.run_dir=next((cls.p/'runs').iterdir());publish(cls.run_dir,cls.out,START,END,BBOX)
        cls.store=PreviewStore(cls.out)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_01_integrity_and_exact_c_values(self):
        import csv
        verify_algorithm()
        self.assertEqual(sha(self.out/'field_posterior.csv'),sha(self.run_dir/'fold_01/full_reconstruction/field_posterior.csv'))
        with (self.out/'field_posterior.csv').open() as f:raw={(r['time'],r['cell_id']):r for r in csv.DictReader(f)}
        self.assertEqual(len(raw),len(self.store.rows))
        for r in self.store.rows:
            for k in ('p_fire','mean_frp_mw','ci95_low_mw','ci95_high_mw'):
                self.assertEqual(r[k],float(raw[r['time'],r['cell_id']][k]))
            self.assertFalse(r['physical_frp_validated'])
        self.assertEqual(set(self.store.metadata['training_observations']),{'modis','viirs'})
        self.assertEqual(self.store.metadata['calibration_kind'],'ILLUSTRATIVE')

    def test_02_pagination_and_geometry(self):
        allrows=self.store.field(str(START),str(END),BBOX,100)['items']
        first=self.store.field(str(START),str(END),BBOX,1)
        self.assertEqual(first['items'],allrows[:1]);self.assertEqual(first['total'],len(allrows))
        self.assertEqual(self.store.field(str(START),str(END),BBOX,1,1)['items'],allrows[1:2])
        self.assertEqual({r['cell_id'] for r in allrows},{f['id'] for f in self.store.geometry['features']})
        self.assertEqual(self.store.field(str(START),str(END),[0,0,1,1])['total'],0)

    def test_03_calendar_and_missing(self):
        rows=self.store.calendar(str(START),str(END),BBOX)['items']
        self.assertEqual(len(rows),31)
        self.assertAlmostEqual(rows[0]['expected_active_cell_time_bins'],sum(r['p_fire'] for r in self.store.rows))
        self.assertEqual(rows[0]['observed_cell_time_bins'],sum(r['coverage_status']=='observed' for r in self.store.rows))
        self.assertTrue(all(r['coverage_status']=='no_data' and r['expected_active_cell_time_bins'] is None for r in rows[1:]))
        with self.assertRaises(ValueError):self.store.field(str(END),str(START),BBOX)
        with self.assertRaises(ValueError):self.store.field(str(START),str(END),BBOX,-1)

    def test_04_separate_validation(self):
        v=self.store.validation
        self.assertIn('separate withheld-granule',v['scope'])
        self.assertTrue(v['comparison']['actual_fusion']);self.assertGreater(v['comparison']['n'],0)
        self.assertEqual(json.loads((self.out/'report.json').read_text())['holdout_viirs'],0)
        self.assertEqual(json.loads((self.out/'report.json').read_text())['holdout_modis'],0)

    def test_05_tamper_refusal(self):
        d=self.p/'tampered';shutil.copytree(self.out,d)
        with (d/'field.json').open('a') as f:f.write(' ')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):PreviewStore(d)

    def test_06_warning_and_input_mismatch_refusal(self):
        for name,rel in [('warning','fold_01/full_reconstruction/report.json'),('wrong_input','fold_01/input/field_all.txt')]:
            d=self.p/name;shutil.copytree(self.run_dir,d);p=d/rel
            if name=='warning':
                r=json.loads(p.read_text());r['warning']=True;p.write_text(json.dumps(r))
            else:p.write_bytes(p.read_bytes()+b'\n')
            out=self.p/(name+'_output')
            with self.assertRaisesRegex(ValueError,'No eligible full reconstruction'):publish(d,out,START,END,BBOX)
            self.assertFalse(out.exists())

    def test_07_refuse_existing_or_outside_date(self):
        with self.assertRaisesRegex(ValueError,'output exists'):publish(self.run_dir,self.out,START,END,BBOX)
        with self.assertRaisesRegex(ValueError,'No eligible full reconstruction'):publish(self.run_dir,self.p/'wrong_date',date(2024,1,1),date(2024,1,2),BBOX)


if __name__=='__main__':unittest.main(verbosity=2)
