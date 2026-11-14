from __future__ import annotations
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_database import connect, store
from phase2.phase2_dataset_builder import build_model_input
from phase2.phase2_metrics import METRICS, compute_metrics
from phase2.phase2_model_interface import list_runs, load_predictions, run_model
from phase2.phase2_schema import columns_of

# validation of a harmonization run (task 2.14):
# compare its predictions with the reference (summed VIIRS FRP) per split and per group,
# next to the no-correction identity baseline, save the numbers and make plots.

VALIDATION_COLS = columns_of('model_validation_results')
GROUPS = ['all', 'modis_satellite', 'daynight', 'region', 'month', 'n_viirs_bin', 'frp_bin']
N_VIIRS_BINS = ([0, 1, 5, 20, np.inf], ['1', '2-5', '6-20', '>20'])
FRP_BINS = ([-np.inf, 10, 50, 200, np.inf], ['<10 MW', '10-50 MW', '50-200 MW', '>200 MW'])


def split_method_of(dataset_version: str) -> str:
    """'2.12.0+cfg2.1.0+event|features:basic' -> 'event'"""
    return dataset_version.split('|')[0].rsplit('+', 1)[-1]


def latest_run(db_path=None, demo=False, exclude_identity=False) -> str:
    runs = list_runs(db_path, demo)
    if exclude_identity:
        runs = runs[runs['model_name'] != 'identity']
    if runs.empty:
        raise RuntimeError('no model runs found: run phase2_model_interface.py first')
    return runs['model_run_id'].iloc[-1]


def baseline_for(run_id: str, db_path=None, demo=False, cfg: Phase2Config | None = None) -> str:
    """Identity run on the same data as run_id (made now if it does not exist yet)."""
    runs = list_runs(db_path, demo).set_index('model_run_id')
    version = runs.loc[run_id, 'dataset_version']
    same = runs[(runs['model_name'] == 'identity') & (runs['dataset_version'] == version)]
    if len(same):
        return same.index[0]
    base_id, _ = run_model('identity', split_method_of(version), db_path, demo, cfg)
    return base_id


def validation_frame(run_id: str, db_path=None, demo=False, cfg: Phase2Config | None = None) -> pd.DataFrame:
    """Predictions of one run + reference value + the columns we group by."""
    cfg = cfg or load_config(demo_mode=demo)
    pred = load_predictions(run_id, db_path, demo)
    if pred.empty:
        raise RuntimeError(f'run {run_id} has no predictions')
    data = build_model_input(split_method_of(pred['dataset_version'].iloc[0]), db_path, demo, cfg)
    keep = ['unit_id', 'reference_value', 'region', 'modis_satellite', 'daynight', 'acq_date', 'n_viirs']
    f = pred.merge(data[[c for c in keep if c in data.columns]], on='unit_id', how='inner')
    f['residual'] = f['predicted_value'] - f['reference_value']
    f['all'] = 'all'
    f['month'] = pd.to_datetime(f['acq_date']).dt.strftime('%Y-%m')
    f['n_viirs_bin'] = pd.cut(f['n_viirs'], N_VIIRS_BINS[0], labels=N_VIIRS_BINS[1]).astype(str)
    f['frp_bin'] = pd.cut(f['source_value'], FRP_BINS[0], labels=FRP_BINS[1]).astype(str)
    return f


def group_metrics(frame: pd.DataFrame, groups=GROUPS) -> pd.DataFrame:
    """Long table: split, group_by, group_value, metric, value, n."""
    rows = []
    for split_name, part in [('all', frame)] + list(frame.groupby('split')):
        for g in groups:
            for value, sub in part.groupby(g, observed=True):
                m = compute_metrics(sub['reference_value'], sub['predicted_value'],
                                    sub['predicted_lower'], sub['predicted_upper'])
                for name in METRICS:
                    rows.append(dict(split=split_name, group_by=g, group_value=str(value),
                                     metric=name, value=m[name], n=m['n']))
    return pd.DataFrame(rows)


def validate(run_id: str | None = None, db_path=None, demo=False, cfg: Phase2Config | None = None,
             save: bool = True, plots: bool = True) -> pd.DataFrame:
    """Validate one run (default: the latest) against the identity baseline.
    Returns model_validation_results rows (+ a 'skill' column: 1 - error / baseline error)."""
    cfg = cfg or load_config(demo_mode=demo)
    run_id = run_id or latest_run(db_path, demo)
    base_id = baseline_for(run_id, db_path, demo, cfg)

    frame = validation_frame(run_id, db_path, demo, cfg)
    res = group_metrics(frame)
    base = group_metrics(validation_frame(base_id, db_path, demo, cfg))
    key = ['split', 'group_by', 'group_value', 'metric']
    res = res.merge(base[key + ['value']].rename(columns={'value': 'baseline_value'}), on=key, how='left')
    res['model_run_id'] = run_id
    res['baseline_run_id'] = base_id
    res['created_at'] = datetime.now(timezone.utc)
    res = res[VALIDATION_COLS]

    if save:
        store(res.dropna(subset=['value']), 'model_validation_results', db_path=db_path, demo=demo)
        folder = cfg.output_dir('reports', 'validation', run_id)
        res.to_csv(folder / 'metrics.csv', index=False)
        (folder / 'summary.md').write_text(summary_text(res, run_id, base_id))
        if plots:
            make_plots(frame, validation_frame(base_id, db_path, demo, cfg), folder)
        print(f'report: {folder}')
    return res.assign(skill=1 - res['value'] / res['baseline_value'])


def summary_text(res: pd.DataFrame, run_id: str, base_id: str) -> str:
    main = res[(res['group_by'] == 'all') & res['metric'].isin(['mae', 'rmse', 'bias', 'log_rmse', 'pearson_r'])]
    table = main.pivot(index='split', columns='metric', values='value').round(3)
    base = main.pivot(index='split', columns='metric', values='baseline_value').round(3)
    return (f'# Validation of {run_id}\n\nbaseline (identity): {base_id}\n\n'
            f'## model\n```\n{table.to_string()}\n```\n## baseline\n```\n{base.to_string()}\n```\n')


def make_plots(frame: pd.DataFrame, base_frame: pd.DataFrame, folder):
    """Scatter (predicted vs reference), residual histogram and MAE per group, test split."""
    try:
        import matplotlib
    except ImportError:
        print('matplotlib not installed: no plots (pip install matplotlib)')
        return
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    test, base_test = frame[frame['split'] == 'test'], base_frame[base_frame['split'] == 'test']
    if test.empty:
        return

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(base_test['reference_value'], base_test['predicted_value'], s=6, alpha=0.4, label='baseline (MODIS)')
    if frame['model_name'].iloc[0] != 'identity':
        ax.scatter(test['reference_value'], test['predicted_value'], s=6, alpha=0.4, label='model')
    top = max(test['reference_value'].max(), test['predicted_value'].max(), 1)
    ax.plot([0.1, top], [0.1, top], 'k--', lw=1)
    ax.set(xscale='log', yscale='log', xlabel='summed VIIRS FRP (MW)', ylabel='predicted FRP (MW)',
           title='test split')
    ax.legend()
    fig.tight_layout()
    fig.savefig(folder / 'scatter_test.png', dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    lim = np.nanpercentile(np.abs(base_test['residual']), 95)
    bins = np.linspace(-lim, lim, 50)
    ax.hist(base_test['residual'], bins=bins, alpha=0.5, label='baseline')
    if frame['model_name'].iloc[0] != 'identity':
        ax.hist(test['residual'], bins=bins, alpha=0.5, label='model')
    ax.axvline(0, color='k', lw=1)
    ax.set(xlabel='predicted - reference (MW)', ylabel='match groups', title='residuals, test split')
    ax.legend()
    fig.tight_layout()
    fig.savefig(folder / 'residuals_test.png', dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for ax, g in zip(axes, ['modis_satellite', 'daynight', 'n_viirs_bin']):
        mae = pd.DataFrame({
            'baseline': base_test.groupby(g)['residual'].apply(lambda r: r.abs().mean()),
            'model': test.groupby(g)['residual'].apply(lambda r: r.abs().mean()),
        })
        mae.plot.bar(ax=ax, rot=0, legend=(g == 'modis_satellite'))
        ax.set(title=f'MAE by {g}', xlabel='', ylabel='MW')
    fig.tight_layout()
    fig.savefig(folder / 'mae_by_group_test.png', dpi=150)
    plt.close(fig)


def get_validation(run_id: str, db_path=None, demo=False) -> pd.DataFrame:
    """Saved validation rows of one run (for the API / frontend later)."""
    with connect(db_path, demo, tables=['model_validation_results']) as con:
        return con.execute('SELECT * FROM model_validation_results WHERE model_run_id = ?', [run_id]).df()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Validate a harmonization run against the baseline (Task 2.14)')
    parser.add_argument('--run', default=None, help='model_run_id (default: latest run)')
    parser.add_argument('--no-plots', action='store_true')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _res = validate(args.run, demo=args.demo, plots=not args.no_plots)
    _all = _res[(_res['group_by'] == 'all') & _res['metric'].isin(['mae', 'rmse', 'bias', 'pearson_r'])]
    print(_all.pivot(index='split', columns='metric', values='value').round(2).to_string())
    print('\nMAE on test by MODIS satellite / day-night:')
    _t = _res[(_res['split'] == 'test') & (_res['metric'] == 'mae') & _res['group_by'].isin(['modis_satellite', 'daynight'])]
    print(_t[['group_by', 'group_value', 'value', 'n']].round(2).to_string(index=False))
