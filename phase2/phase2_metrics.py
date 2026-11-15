from __future__ import annotations
import numpy as np
import pandas as pd

# error numbers for comparing predicted values with reference values (task 2.14)
#   mae / rmse / bias       in MW (bias > 0 means the model gives too much)
#   median_abs_error        less sensitive to a few huge fires
#   log_rmse                rmse of log(1 + value), fair for small and big fires together
#   pearson_r / spearman_r  how well they go up and down together
#   r2                      share of the reference variation explained
#   coverage                share of references inside [lower, upper] (only with intervals)

METRICS = ['mae', 'rmse', 'bias', 'median_abs_error', 'log_rmse',
           'pearson_r', 'spearman_r', 'r2', 'coverage']


def residuals(reference, predicted) -> np.ndarray:
    """predicted - reference (positive = too high)."""
    return np.asarray(predicted, float) - np.asarray(reference, float)


def compute_metrics(reference, predicted, lower=None, upper=None) -> dict:
    """All metrics for one set of rows. Rows with a missing value are skipped."""
    y = np.asarray(reference, float)
    p = np.asarray(predicted, float)
    if y.ndim != 1 or p.ndim != 1 or y.shape != p.shape:
        raise ValueError('reference and predicted must be equal-length one-dimensional arrays')
    if (lower is None) != (upper is None):
        raise ValueError('supply both lower and upper interval bounds')
    if lower is not None:
        lower, upper = np.asarray(lower, float), np.asarray(upper, float)
        if lower.shape != y.shape or upper.shape != y.shape:
            raise ValueError('interval bounds must have the same shape as reference')
        if np.any(np.isfinite(lower) & np.isfinite(upper) & (lower > upper)):
            raise ValueError('lower interval bound exceeds upper')
    if np.any(np.isfinite(y) & (y < 0)) or np.any(np.isfinite(p) & (p < 0)):
        raise ValueError('FRP values must be nonnegative')
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    out = {m: np.nan for m in METRICS}
    out['n'] = int(len(y))
    if len(y) == 0:
        return out

    r = p - y
    out['mae'] = float(np.mean(np.abs(r)))
    out['rmse'] = float(np.sqrt(np.mean(r ** 2)))
    out['bias'] = float(np.mean(r))
    out['median_abs_error'] = float(np.median(np.abs(r)))
    out['log_rmse'] = float(np.sqrt(np.mean((np.log1p(np.clip(p, 0, None)) - np.log1p(np.clip(y, 0, None))) ** 2)))
    if len(y) > 1 and np.std(y) > 0 and np.std(p) > 0:
        out['pearson_r'] = float(np.corrcoef(y, p)[0, 1])
        out['spearman_r'] = float(pd.Series(y).corr(pd.Series(p), method='spearman'))
    if len(y) > 1 and np.var(y) > 0:
        out['r2'] = float(1 - np.sum(r ** 2) / np.sum((y - y.mean()) ** 2))

    if lower is not None and upper is not None:
        lo = np.asarray(lower, float)[ok]
        hi = np.asarray(upper, float)[ok]
        has = np.isfinite(lo) & np.isfinite(hi)
        if has.any():
            out['coverage'] = float(np.mean((y[has] >= lo[has]) & (y[has] <= hi[has])))
    return out
