# Harmonization model interface (task 2.13)

How the harmonization team plugs any method (regression, quantile mapping, hierarchical, ML, Bayesian, ...) into Phase 2. The coding team provides only this interface and a no-correction baseline.

## 1. Data a model gets
From `phase2_dataset_builder.build_model_input()` (task 2.12). One row per **match group** (one MODIS detection + the VIIRS detections matched to it):

| Column | Meaning |
|---|---|
| `unit_id` | match group id |
| `split` | `train` / `validation` / `test` (no fire event is in two splits) |
| `source_value` | MODIS FRP (MW), the value to convert |
| `reference_value` | summed VIIRS FRP (MW), the answer; only used in `fit()` and validation |
| features | `n_viirs`, pixel areas, brightness temperatures, distance, time difference, satellite, day/night, ... (task 2.10 when available, otherwise a basic set) |

## 2. Writing a model
```python
import pandas as pd
from phase2.phase2_model_interface import HarmonizationModel, register_model, run_model

@register_model
class MyModel(HarmonizationModel):
    name, version = 'my_model', '0.1'

    def fit(self, train):                       # train split only
        self.k = train['reference_value'].sum() / train['source_value'].sum()
        return self

    def predict(self, data):                    # data has NO reference_value
        p = data['source_value'] * self.k
        return pd.DataFrame({'unit_id': data['unit_id'], 'predicted_value': p})

    def parameters(self):                       # saved with the run
        return {'k': float(self.k)}

run_id, predictions = run_model('my_model')     # fit on train, predict all splits, check, save
```
Optional: return `predicted_lower` / `predicted_upper` for an uncertainty interval.

## 3. What happens in `run_model()`
1. Loads the model input (2.12) for the chosen split method (`event` by default).
2. `fit()` on the train split.
3. `predict()` on all splits, with `reference_value` removed so the model cannot cheat.
4. Checks the output: one row per unit, numbers only, no infinities, prediction inside its interval.
5. Saves `model_runs` (name, version, parameters, dataset version) and `model_predictions`. Reruns with the same model, data and parameters give the same `model_run_id` and add no duplicates.

## 4. Baseline
`identity`: predicted value = MODIS value, no correction. Run it with `python -m phase2.phase2_model_interface`. Every real model is compared against it in validation (task 2.14).

## 5. Useful functions
- `list_runs()` shows all saved runs
- `load_predictions(run_id)` gives the predictions of one run
- `get_model(name)` returns a registered model

## 6. Notes
- About 0.5% of BC July 2023 detections are not vegetation fires (FIRMS types 2 and 3: industrial and offshore; see task 2.9, `phase2_source_flags.flag_observations()`). Consider excluding them when fitting.
- Per matched group, summed VIIRS FRP and MODIS FRP are already close (median 43 vs 44 MW). The large raw disagreement comes mainly from pixel size and from small fires only VIIRS detects.

## Scientific field-model boundary
The unchanged C engine is in `phase2/algorithm/`. It is not a match-group regression
subclass. Its field posterior is indexed by its own `cell_id` and time bin, with an
explicit footprint operator and coverage state. Do not convert positive FIRMS-only
rows into fictitious non-detections or reuse the engineering grid IDs as algorithm
IDs. The new runner executes both workflows but keeps their outputs separate.

The match-group predictor now also removes `viirs_frp_sum_mw`, `viirs_frp_max_mw`
and `log_frp_viirs_sum` (if present) from prediction inputs. Other target-side
features such as counts, geometry and time differences may be unavailable in a
MODIS-only historical period. A future model must define and test its own
source-only feature contract. The identity baseline is unchanged.
