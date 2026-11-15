from __future__ import annotations
import numpy as np
import pandas as pd

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_database import connect, store
from phase2.phase2_schema import columns_of

SPLIT_COLS = columns_of('dataset_splits')

# train / validation / test splits that never put the same fire in two splits.
# units are match groups (task 2.6); they are split in whole groups:
#   event     whole fire events (task 2.7), in random order        <- default
#   time      whole fire events in time order (oldest -> train, newest -> test)
#   backcast  whole fire events in reverse time order (newest -> train, oldest -> test)
#   region    whole space blocks of block_deg x block_deg degrees, in random order
#   random    single match groups, in random order (leaks: only for comparison)


def split_version(cfg: Phase2Config, method: str) -> str:
    return f'{cfg.version("splits")}+{method}'


def _assign(group_order: pd.Series, group_sizes: pd.Series, cfg: Phase2Config) -> pd.Series:
    """Walk the groups in group_order and give each one a split, so that the share of
    units per split follows cfg.splits.fractions. Returns split per group."""
    sizes = group_sizes.loc[group_order].to_numpy(float)
    middle = (np.cumsum(sizes) - sizes / 2) / sizes.sum()   # where each group sits, 0..1
    bounds = np.cumsum(cfg.splits.fractions)[:-1]
    names = np.array(cfg.splits.names)
    return pd.Series(names[np.searchsorted(bounds, middle, side='right')], index=group_order)


def split_units(units: pd.DataFrame, method: str, cfg: Phase2Config | None = None) -> pd.DataFrame:
    """units: one row per unit with unit_id, event_id, time, latitude, longitude.
    Returns unit_id, split, group_id (the thing kept together)."""
    cfg = cfg or load_config()
    if method not in cfg.splits.methods:
        raise ValueError(f'unknown split method {method!r}, use one of {cfg.splits.methods}')
    if units.empty:
        return pd.DataFrame(columns=['unit_id', 'split', 'group_id'])
    rng = np.random.default_rng(cfg.splits.seed)
    u = units.copy()

    if method in ('event', 'time', 'backcast'):
        u['group_id'] = u['event_id'].fillna(u['unit_id'])
    elif method == 'region':
        # a fire event goes to the block of its centre, so it is never cut in two
        u['group_id'] = u['event_id'].fillna(u['unit_id'])
        centre = u.groupby('group_id')[['latitude', 'longitude']].transform('mean')
        b = cfg.splits.block_deg
        u['group_id'] = ('blk_' + np.floor(centre['latitude'] / b).astype(int).astype(str) + '_'
                         + np.floor(centre['longitude'] / b).astype(int).astype(str))
    else:  # random
        u['group_id'] = u['unit_id']

    sizes = u.groupby('group_id').size()
    if method == 'time':
        order = u.groupby('group_id')['time'].min().sort_values(kind='stable').index
    elif method == 'backcast':
        order = u.groupby('group_id')['time'].min().sort_values(ascending=False, kind='stable').index
    else:
        groups = np.sort(sizes.index.to_numpy())
        order = pd.Index(groups[rng.permutation(len(groups))])
    split_of_group = _assign(pd.Series(order), sizes, cfg)
    u['split'] = u['group_id'].map(split_of_group)
    return u[['unit_id', 'split', 'group_id']].reset_index(drop=True)


def match_group_units(db_path=None, demo=False, cfg: Phase2Config | None = None) -> pd.DataFrame:
    """One row per match group (task 2.6) with its fire event (task 2.7), time and place."""
    cfg = cfg or load_config(demo_mode=demo)
    sql = '''
        SELECT mt.match_group_id AS unit_id,
               any_value(e.event_id) AS event_id,
               any_value(o.acq_datetime_utc) AS time,
               any_value(o.latitude) AS latitude,
               any_value(o.longitude) AS longitude
        FROM matched_observations mt
        JOIN observations o ON o.observation_id = mt.modis_observation_id
        LEFT JOIN fire_event_observations e
               ON e.observation_id = mt.modis_observation_id AND e.dataset_version = ?
        WHERE mt.dataset_version = ?
        GROUP BY mt.match_group_id
        ORDER BY mt.match_group_id
    '''
    with connect(db_path, demo, tables=['matched_observations', 'fire_event_observations']) as con:
        return con.execute(sql, [cfg.version('events'), cfg.version('matching')]).df()


def make_splits(method: str | None = None, db_path=None, demo=False,
                cfg: Phase2Config | None = None, save: bool = True) -> pd.DataFrame:
    """Build the dataset_splits rows for all match groups and (optionally) save them."""
    cfg = cfg or load_config(demo_mode=demo)
    method = method or cfg.splits.default_method
    units = match_group_units(db_path, demo, cfg)
    if units.empty:
        raise RuntimeError('no match groups found: run phase2_matching.py and phase2_fire_events.py first')
    if method != 'random' and units['event_id'].isna().all():
        raise RuntimeError(
            'no fire events found: run the events step (python -m phase2.phase2_run --only events) before splitting'
        )
    s = split_units(units, method, cfg)
    s['unit_type'] = 'match_group'
    s['split_method'] = method
    s['seed'] = cfg.splits.seed
    s['dataset_version'] = split_version(cfg, method)
    s = s[SPLIT_COLS]
    if save:
        store(s, 'dataset_splits', db_path=db_path, demo=demo)
    return s


def check_no_leak(splits: pd.DataFrame) -> bool:
    """True when every group (fire event / block) sits in exactly one split."""
    return bool((splits.groupby('group_id')['split'].nunique() <= 1).all())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Train/validation/test splits (Task 2.12)')
    parser.add_argument('--method', default=None, help='event (default), time, backcast, region or random')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _cfg = load_config(demo_mode=True) if args.demo else load_config()
    _s = make_splits(args.method, demo=args.demo, cfg=_cfg)
    _m = args.method or _cfg.splits.default_method
    print(f'method: {_m} | version {split_version(_cfg, _m)} | seed {_cfg.splits.seed}')
    summary = _s.groupby('split').agg(match_groups=('unit_id', 'size'), groups_kept_together=('group_id', 'nunique'))
    summary['share'] = (summary['match_groups'] / summary['match_groups'].sum()).round(3)
    print(summary.reindex(_cfg.splits.names).to_string())
    if _m == 'random':
        print('note: random splits single match groups, so one fire can be in two splits (comparison only)')
    else:
        print('same fire in two splits:', 'no' if check_no_leak(_s) else 'YES')