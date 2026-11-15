from __future__ import annotations
from datetime import datetime, timezone
import json

import pandas as pd

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_database import connect, store
from phase2.phase2_dataset_builder import build_model_input
from phase2.phase2_prediction_schema import RUN_COLUMNS, check_model_output, to_prediction_rows
from phase2.phase2_schema import model_run_id

# the "plug" every harmonization method uses (task 2.13).
# the coding team builds only this interface + a no-correction baseline;
# the real methods (regression, hierarchical, ML, Bayesian, ...) are written by the
# harmonization team as subclasses of HarmonizationModel.
#
#   class MyModel(HarmonizationModel):
#       name, version = 'my_model', '0.1'
#       def fit(self, train): ...learn from train['source_value'] vs train['reference_value']...
#       def predict(self, data): return pd.DataFrame({'unit_id': ..., 'predicted_value': ...})
#
#   register_model(MyModel); run_model('my_model')


class HarmonizationModel:
    """Base class. Input rows come from phase2_dataset_builder.build_model_input()."""
    name = 'base'
    version = '0'
    unit_type = 'match_group'

    def fit(self, train: pd.DataFrame) -> 'HarmonizationModel':
        """Learn from the train split. train has source_value, reference_value and features."""
        return self

    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return unit_id, predicted_value and optionally predicted_lower / predicted_upper.
        Must NOT use data['reference_value'] (that is the answer)."""
        raise NotImplementedError

    def parameters(self) -> dict:
        """Settings / fitted values to store with the run (must be JSON friendly)."""
        return {}


class IdentityModel(HarmonizationModel):
    """No-correction baseline: the harmonized value is just the MODIS value.
    Every real model must beat this one (task 2.14 compares against it)."""
    name = 'identity'
    version = '1.0'

    def predict(self, data):
        return pd.DataFrame({'unit_id': data['unit_id'], 'predicted_value': data['source_value']})


MODELS: dict[str, type[HarmonizationModel]] = {}


def register_model(model_class: type[HarmonizationModel]) -> type[HarmonizationModel]:
    """Make a model available by name (can be used as a @register_model decorator)."""
    if not issubclass(model_class, HarmonizationModel):
        raise TypeError('models must subclass HarmonizationModel')
    MODELS[model_class.name] = model_class
    return model_class


register_model(IdentityModel)


def get_model(name: str, **settings) -> HarmonizationModel:
    try:
        return MODELS[name](**settings)
    except KeyError:
        raise ValueError(f'unknown model {name!r}, registered: {sorted(MODELS)}') from None


def run_model(model: HarmonizationModel | str | None = None, method: str | None = None,
              db_path=None, demo=False, cfg: Phase2Config | None = None,
              save: bool = True, is_synthetic: bool | None = None) -> tuple[str, pd.DataFrame]:
    """Fit on the train split, predict every split, check the output, save the run.
    Returns (model_run_id, predictions in model_predictions layout)."""
    cfg = cfg or load_config(demo_mode=demo)
    if model is None or isinstance(model, str):
        model = get_model(model or cfg.model.default_model)
    data = build_model_input(method, db_path, demo, cfg)
    if data.empty:
        raise RuntimeError('model input is empty: run matching, fire events and splits first')

    model.fit(data[data['split'] == 'train'].reset_index(drop=True))
    # The summed VIIRS FRP also appears under a feature alias; max FRP is
    # derived from the same target-side measurements. Neither is a predictor.
    answer_free = data.drop(columns=['reference_value', 'viirs_frp_sum_mw',
                                     'viirs_frp_max_mw', 'log_frp_viirs_sum'], errors='ignore')
    output = check_model_output(model.predict(answer_free), data)

    dataset_version = f'{data["split_version"].iloc[0]}|features:{data["feature_source"].iloc[0]}'
    params = model.parameters()
    run_id = model_run_id(model.name, model.version, dataset_version, params)
    predictions = to_prediction_rows(output, data, run_id)

    if save:
        run = pd.DataFrame([{
            'model_run_id': run_id, 'model_name': model.name, 'model_version': model.version,
            'target': cfg.model.target, 'unit_type': model.unit_type,
            'dataset_version': dataset_version, 'parameters': json.dumps(params, default=str),
            'is_synthetic': bool(cfg.demo_mode if is_synthetic is None else is_synthetic),
            'created_at': datetime.now(timezone.utc),
        }])[RUN_COLUMNS]
        store(run, 'model_runs', db_path=db_path, demo=demo)
        store(predictions, 'model_predictions', db_path=db_path, demo=demo)
    return run_id, predictions


def load_predictions(run_id: str, db_path=None, demo=False) -> pd.DataFrame:
    """Predictions of one run joined with the reference value, ready for validation (2.14)."""
    sql = '''
        SELECT p.*, r.model_name, r.model_version, r.dataset_version
        FROM model_predictions p JOIN model_runs r USING (model_run_id)
        WHERE p.model_run_id = ?
    '''
    with connect(db_path, demo, tables=['model_runs', 'model_predictions']) as con:
        return con.execute(sql, [run_id]).df()


def list_runs(db_path=None, demo=False) -> pd.DataFrame:
    with connect(db_path, demo, tables=['model_runs']) as con:
        return con.execute('SELECT * FROM model_runs ORDER BY created_at').df()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run a harmonization model through the interface (Task 2.13)')
    parser.add_argument('--model', default=None, help=f'registered: {sorted(MODELS)}')
    parser.add_argument('--method', default=None, help='split method (default from config)')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _run_id, _pred = run_model(args.model, args.method, demo=args.demo)
    print(f'run: {_run_id}')
    print(_pred.groupby('split').agg(rows=('unit_id', 'size'),
                                     predicted_median=('predicted_value', 'median')).round(1).to_string())
    print(f'runs saved so far: {len(list_runs(demo=args.demo))}')