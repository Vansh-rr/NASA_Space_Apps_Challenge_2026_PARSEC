"""Failures reproduced during the repository review."""
import numpy as np
import pandas as pd
import pytest
from conftest import obs_row
from phase2.phase2_database import connect, load, migrate_table, store
from phase2.phase2_schema import columns_of
from phase2.phase2_prediction_schema import check_model_output
from phase2.phase2_metrics import compute_metrics
from phase2.phase2_history import build_history
from phase2.phase2_model_interface import input_version, run_model
from phase2.phase2_validation import validate
from test_phase2_model_interface import prepared_db


def test_empty_store_creates_schema_and_empty_table_list_means_none(tmp_path):
    db = tmp_path/'empty.duckdb'
    with connect(db, tables=[]) as con:
        assert [r[0] for r in con.execute('SHOW TABLES').fetchall()] == ['observations']
    assert store(pd.DataFrame(columns=columns_of('fire_anomalies')), 'fire_anomalies', db) == 0
    with connect(db, tables=[]) as con:
        assert con.execute('SELECT COUNT(*) FROM fire_anomalies').fetchone()[0] == 0
    assert load('fire_anomalies', db, where={'region': []}).empty
    with pytest.raises(ValueError): migrate_table('observations; DROP TABLE observations',db)


@pytest.mark.parametrize('values,extra', [([np.nan,1],{}), ([-1,1],{}),
    ([1,2],{'predicted_lower':[0,1]}), ([1,2],{'predicted_lower':[-1,0],'predicted_upper':[3,3]})])
def test_invalid_predictions_fail_instead_of_disappearing_from_metrics(values, extra):
    inp = pd.DataFrame({'unit_id':['a','b']})
    with pytest.raises(ValueError):
        check_model_output(pd.DataFrame(dict(unit_id=['a','b'],predicted_value=values,**extra)), inp)


def test_metrics_reject_broadcasting_and_reversed_intervals():
    with pytest.raises(ValueError): compute_metrics([1,2],[1])
    with pytest.raises(ValueError): compute_metrics([1,2],[[1],[2]])
    with pytest.raises(ValueError): compute_metrics([1,2],[1,2],lower=[0,0],upper=[2])
    with pytest.raises(ValueError): compute_metrics([1],[1],lower=[2],upper=[0])
    with pytest.raises(ValueError): compute_metrics([1],[-2])


def test_verified_coverage_is_needed_for_zero_or_complete_month(cfg):
    obs = pd.DataFrame([obs_row('m','MODIS','Aqua',53,-122,frp=np.nan)])
    obs['is_flagged'] = False
    unknown = build_history(obs, 'day','british_columbia','2023-07-10','2023-07-11',cfg)
    aqua = unknown[unknown.satellite.eq('Aqua')]
    assert list(aqua.coverage_state) == ['partial_observed','unknown']
    assert aqua.frp_sum_mw.isna().all()
    verified = pd.DataFrame({'satellite':['Aqua','Aqua'], 'date':['2023-07-10','2023-07-11'],
                             'support_evidence':['TEST ONLY complete region QA']*2})
    complete = build_history(obs,'day','british_columbia','2023-07-10','2023-07-11',cfg,verified_coverage=verified)
    aqua = complete[complete.satellite.eq('Aqua')]
    assert list(aqua.coverage_state) == ['observed','no_detections']
    assert list(aqua.n_detections) == [1,0]


def test_changed_inputs_get_new_run_id_and_old_validation_refuses(prepared_db,cfg):
    from phase2.phase2_dataset_builder import build_model_input
    before, _ = run_model('identity', db_path=prepared_db,cfg=cfg)
    with connect(prepared_db,tables=[]) as con:
        con.execute("UPDATE observations SET frp_mw = frp_mw + 1 WHERE sensor_family = 'MODIS'")
    with pytest.raises(RuntimeError,match='changed'):
        validate(before,db_path=prepared_db,cfg=cfg,plots=False)
    after, _ = run_model('identity',db_path=prepared_db,cfg=cfg)
    assert after != before
    data = build_model_input(db_path=prepared_db,cfg=cfg)
    assert input_version(data) == input_version(data.sample(frac=1,random_state=3))


def test_config_values_change_derived_versions(cfg):
    matching=cfg.matching.model_copy(update={'max_time_diff_minutes':5})
    altered=cfg.model_copy(update={'matching':matching})
    assert altered.version('matching') != cfg.version('matching')
    assert cfg.model_copy(update={'demo_mode':True}).version('matching') == cfg.version('matching')


def test_store_refreshes_derived_values(tmp_path):
    db=tmp_path/'derived.duckdb'
    cols=columns_of('dataset_splits')
    frame=pd.DataFrame([dict(unit_id='a',unit_type='match_group',split='train',group_id='g',
                              split_method='event',seed=42,dataset_version='test')],columns=cols)
    assert store(frame,'dataset_splits',db) == 1
    frame['split']='test'
    assert store(frame,'dataset_splits',db) == 0
    assert load('dataset_splits',db).split.iloc[0] == 'test'


def test_resume_uses_selected_database_instead_of_shared_parquet(phase1_db,cfg,tmp_path):
    from phase2.phase2_run import _overlap
    from phase2.phase2_overlap import save_overlap
    # Poison the shared export: resume must still read the requested database.
    save_overlap(pd.DataFrame(),cfg=cfg)
    data=_overlap(dict(cfg=cfg,db=phase1_db,region='british_columbia',start='2023-07-01',end='2023-07-05'))
    assert len(data) == 405
