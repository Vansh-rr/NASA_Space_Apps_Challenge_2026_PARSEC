from __future__ import annotations
import json
import time
from datetime import datetime, timezone

import pandas as pd

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_database import db_path_for, store, table_counts

# one command for all of phase 2 (task 2.18), in the right order:
#   flags -> overlap -> grid -> matching -> events -> comparison -> features -> splits
#   -> datasets -> baseline -> validation
# every step reads what the step before saved, so you can also start in the middle
# (--from events) or run one step (--only splits). reruns add no duplicate rows.

STEPS = ['flags', 'overlap', 'grid', 'matching', 'events', 'comparison',
         'features', 'splits', 'datasets', 'baseline', 'validation']


def step_flags(ctx):
    from phase2.phase2_source_flags import save_registry
    return {'flags': save_registry(db_path=ctx['db'])}


def step_overlap(ctx):
    from phase2.phase2_overlap import extract_overlap, save_overlap, store_overlap_table
    obs = extract_overlap(cfg=ctx['cfg'], db_path=ctx['db'], region=ctx['region'],
                          start=ctx['start'], end=ctx['end'])
    if obs.empty:
        raise RuntimeError('no overlap detections: check the region / dates and that phase 1 ran')
    save_overlap(obs, cfg=ctx['cfg'], region_key=ctx['region'])
    store_overlap_table(obs, db_path=ctx['db'])
    ctx['overlap'] = obs
    return {'detections': len(obs)}


def _overlap(ctx):
    from phase2.phase2_overlap import load_overlap
    if 'overlap' not in ctx:
        ctx['overlap'] = load_overlap(ctx['region'], cfg=ctx['cfg'])
    return ctx['overlap']


def step_grid(ctx):
    from phase2.phase2_grid import grid_config_from_team, assign_cells, build_grid_cells, export_grid
    from phase2.phase2_database import grid_cells_for_db
    cfg = ctx['cfg']
    grid_cfg = grid_config_from_team(ctx['region'], cfg)
    obs = _overlap(ctx)
    assignments = pd.concat([assign_cells(obs, grid_cfg, size) for size in grid_cfg.cell_sizes_km],
                            ignore_index=True)
    cells = build_grid_cells(assignments, grid_cfg)
    store(grid_cells_for_db(cells), 'grid_cells', db_path=ctx['db'])
    store(assignments, 'grid_observations', db_path=ctx['db'])
    export_grid(cells, assignments, cfg.output_dir('grid', ctx['region']))
    return {'cells': len(cells), 'assignments': len(assignments)}


def step_matching(ctx):
    from phase2.phase2_matching import run_matching
    r = run_matching(_overlap(ctx), ctx['cfg'])
    for df, table in [(r.overpasses, 'overpass_groups'), (r.candidates, 'match_candidates'),
                      (r.matched, 'matched_observations'), (r.unmatched, 'unmatched_observations')]:
        store(df, table, db_path=ctx['db'])
    return {'match_groups': r.matched['match_group_id'].nunique(), 'unmatched': len(r.unmatched)}


def step_events(ctx):
    from phase2.phase2_fire_events import build_fire_events
    events, members = build_fire_events(_overlap(ctx), ctx['cfg'])
    store(events, 'fire_events', db_path=ctx['db'])
    store(members, 'fire_event_observations', db_path=ctx['db'])
    return {'fire_events': len(events)}


def step_comparison(ctx):
    from phase2.phase2_database import connect
    from phase2.phase2_sensor_comparison import (build_comparison_pairs, compute_comparison_stats,
                                                  aggregate_groups)
    cfg = ctx['cfg']
    filters = [cfg.version('matching'), ctx['region']]
    where = 'WHERE dataset_version = ? AND region = ?'
    with connect(ctx['db'], tables=['matched_observations']) as con:
        matched = con.execute(f'SELECT * FROM matched_observations {where}', filters).df()
        observations = con.execute(f'''SELECT observation_id, acq_date, frp_mw, delta_bt_k,
            pixel_area_km2, mid_ir_bt_k, confidence_numeric, confidence_class FROM observations
            WHERE observation_id IN (SELECT modis_observation_id FROM matched_observations {where}
              UNION SELECT viirs_observation_id FROM matched_observations {where})''', filters * 2).df()
    if matched.empty:
        raise RuntimeError('no matched detections for comparison; check region/dates or run matching first')
    pairs = build_comparison_pairs(matched, observations)
    folder = cfg.output_dir('comparison', ctx['region'])
    pairs.to_parquet(folder / 'raw_pairs.parquet', index=False)
    aggregate_groups(pairs).to_parquet(folder / 'raw_match_groups.parquet', index=False)
    compute_comparison_stats(pairs).to_csv(folder / 'raw_sensor_statistics.csv', index=False)
    return {'raw_pairs': len(pairs), 'reference': 'sensor agreement, not independent truth'}


def step_features(ctx):
    from phase2.phase2_features import run_features
    return {'feature_rows': len(run_features(db_path=ctx['db'], region=ctx['region'], cfg=ctx['cfg']))}


def step_splits(ctx):
    from phase2.phase2_splits import check_no_leak, make_splits
    s = make_splits(ctx['method'], db_path=ctx['db'], cfg=ctx['cfg'])
    return {**s['split'].value_counts().to_dict(), 'leak_free': check_no_leak(s)}


def step_datasets(ctx):
    from phase2.phase2_dataset_builder import export_model_input
    paths = export_model_input(ctx['method'], db_path=ctx['db'], cfg=ctx['cfg'])
    return {key: str(path) for key, path in paths.items()}


def step_baseline(ctx):
    from phase2.phase2_model_interface import run_model
    ctx['run_id'], pred = run_model(ctx['model'], ctx['method'], db_path=ctx['db'], cfg=ctx['cfg'])
    return {'run': ctx['run_id'], 'predictions': len(pred)}


def step_validation(ctx):
    from phase2.phase2_validation import validate
    res = validate(ctx.get('run_id'), db_path=ctx['db'], cfg=ctx['cfg'], plots=ctx['plots'])
    test = res[(res['split'] == 'test') & (res['group_by'] == 'all')].set_index('metric')['value']
    return {'test_mae': round(test['mae'], 2) if 'mae' in test else None,
            'test_r': round(test['pearson_r'], 3) if 'pearson_r' in test else None,
            'test_split_available': 'mae' in test}


def run_pipeline(steps=None, region=None, start=None, end=None, method=None, model=None,
                 db_path=None, demo=False, cfg: Phase2Config | None = None, plots=True) -> pd.DataFrame:
    """Run the given steps (default all) in order. Returns one row per step with what it did."""
    cfg = cfg or load_config(demo_mode=demo)
    steps = steps or STEPS
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise ValueError(f'unknown steps {unknown}, use {STEPS}')
    ctx = dict(cfg=cfg, db=db_path_for(demo, db_path), region=region or cfg.default_region,
               start=start, end=end, method=method or cfg.splits.default_method,
               model=model or cfg.model.default_model, plots=plots)

    log = []
    for name in [s for s in STEPS if s in steps]:          # always in pipeline order
        print(f'\n=== {name} ===')
        t0 = time.time()
        result = globals()[f'step_{name}'](ctx)
        log.append({'step': name, 'seconds': round(time.time() - t0, 1),
                    'result': json.dumps(result, default=str)})
    log = pd.DataFrame(log)

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    log.to_csv(cfg.output_dir('runs') / f'pipeline_{stamp}.csv', index=False)
    return log


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run Phase 2 end to end (Task 2.18)')
    parser.add_argument('--from', dest='start_step', choices=STEPS, help='start at this step')
    parser.add_argument('--only', choices=STEPS, action='append', help='run only this step (repeatable)')
    parser.add_argument('--region', default=None)
    parser.add_argument('--start', default=None, help='first date, e.g. 2023-07-01')
    parser.add_argument('--end', default=None, help='last date')
    parser.add_argument('--method', default=None, help='split method: event, time, region, random')
    parser.add_argument('--model', default=None, help='registered model (default identity)')
    parser.add_argument('--no-plots', action='store_true')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _steps = args.only or (STEPS[STEPS.index(args.start_step):] if args.start_step else STEPS)
    _log = run_pipeline(_steps, args.region, args.start, args.end, args.method, args.model,
                        demo=args.demo, plots=not args.no_plots)
    print('\n=== done ===')
    print(_log.to_string(index=False))
    print(f'\n{table_counts(demo=args.demo).to_string(index=False)}')