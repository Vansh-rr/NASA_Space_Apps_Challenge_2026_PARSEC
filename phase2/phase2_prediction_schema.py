from __future__ import annotations
import numpy as np
import pandas as pd

from phase2.phase2_schema import PREDICTION_COLUMNS, columns_of

# what every harmonization model must give back (task 2.13)
# one row per unit it was asked about:
#   unit_id          which match group / grid cell / event
#   predicted_value  the harmonized value (e.g. MODIS FRP converted to the VIIRS scale)
#   predicted_lower  optional lower bound of the uncertainty interval
#   predicted_upper  optional upper bound
MODEL_OUTPUT_REQUIRED = ['unit_id', 'predicted_value']
MODEL_OUTPUT_OPTIONAL = ['predicted_lower', 'predicted_upper']
RUN_COLUMNS = columns_of('model_runs')


def check_model_output(output: pd.DataFrame, model_input: pd.DataFrame) -> pd.DataFrame:
    """Check what a model returned and return it with the optional columns filled (NaN).
    Raises ValueError with a clear message when something is wrong."""
    missing = [c for c in MODEL_OUTPUT_REQUIRED if c not in output.columns]
    if missing:
        raise ValueError(f'model output is missing columns: {missing}')
    out = output.copy()
    for col in MODEL_OUTPUT_OPTIONAL:
        if col not in out.columns:
            out[col] = np.nan

    if out['unit_id'].duplicated().any():
        raise ValueError('model output has more than one row for the same unit_id')
    expected, got = set(model_input['unit_id']), set(out['unit_id'])
    if got != expected:
        raise ValueError(f'model output units do not match its input '
                         f'({len(expected - got)} missing, {len(got - expected)} unknown)')

    for col in ['predicted_value'] + MODEL_OUTPUT_OPTIONAL:
        values = pd.to_numeric(out[col], errors='coerce')
        if values.isna().sum() > out[col].isna().sum():
            raise ValueError(f'{col} contains values that are not numbers')
        if np.isinf(values).any():
            raise ValueError(f'{col} contains infinite values')
        out[col] = values

    if out['predicted_value'].isna().any():
        raise ValueError('predicted_value must be finite for every requested unit')
    if (out[['predicted_value'] + MODEL_OUTPUT_OPTIONAL] < 0).any().any():
        raise ValueError('FRP predictions and interval bounds must be nonnegative')
    if (out['predicted_lower'].notna() != out['predicted_upper'].notna()).any():
        raise ValueError('interval bounds must both be supplied or both be missing')

    has_both = out['predicted_lower'].notna() & out['predicted_upper'].notna()
    bad = has_both & ~((out['predicted_lower'] <= out['predicted_value'])
                       & (out['predicted_value'] <= out['predicted_upper']))
    if bad.any():
        raise ValueError(f'{int(bad.sum())} rows where predicted_value is outside '
                         '[predicted_lower, predicted_upper]')
    return out


def to_prediction_rows(output: pd.DataFrame, model_input: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """Model output + input -> model_predictions table rows."""
    keep = model_input[['unit_id', 'unit_type', 'split', 'source_value']]
    rows = keep.merge(output[MODEL_OUTPUT_REQUIRED + MODEL_OUTPUT_OPTIONAL], on='unit_id')
    rows['model_run_id'] = run_id
    return rows[PREDICTION_COLUMNS]
