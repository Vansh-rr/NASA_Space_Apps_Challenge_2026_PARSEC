from __future__ import annotations
 
from typing import NamedTuple
 
import numpy as np
import pandas as pd
 
from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_schema import columns_of, match_group_id as make_match_group_id
from phase2.phase2_temporal import (
    assign_overpasses,
    build_overpass_groups,
    build_overpass_pairs,
)
from phase2.phase2_spatial_matching import build_match_candidates, find_unmatched
 
MATCHED_COLS   = columns_of('matched_observations')
UNMATCHED_COLS = columns_of('unmatched_observations')
 
class MatchResult(NamedTuple):
    matched:    pd.DataFrame   # matched_observations shape
    unmatched:  pd.DataFrame   # unmatched_observations shape
    summary:    dict
    overpasses: pd.DataFrame = pd.DataFrame(columns=columns_of('overpass_groups'))
    candidates: pd.DataFrame = pd.DataFrame(columns=columns_of('match_candidates'))
 
# helpers 
def _outside_overlap_rows(obs: pd.DataFrame, cfg: Phase2Config,
                          dataset_version: str) -> pd.DataFrame:
    """Observations acquired before cfg.overlap_period.start."""
    ol_start = pd.Timestamp(cfg.overlap_period.start, tz='UTC')
    times = pd.to_datetime(obs['acq_datetime_utc'], utc=True)
    mask  = times < ol_start
    pre   = obs[mask]
    if pre.empty:
        return pd.DataFrame(columns=UNMATCHED_COLS)
    return pd.DataFrame({
        'observation_id':   pre['observation_id'].to_numpy(),
        'region':           pre['region'].to_numpy(),
        'sensor_family':    pre['sensor_family'].to_numpy(),
        'satellite':        pre['satellite'].to_numpy(),
        'acq_datetime_utc': times[mask].to_numpy(),
        'reason':           'outside_overlap',
        'dataset_version':  dataset_version,
    })[UNMATCHED_COLS]
 
 
def _apply_cap_and_build_groups(
    candidates: pd.DataFrame,
    obs: pd.DataFrame,
    cfg: Phase2Config,
    config_version: str,
    dataset_version: str,
) -> tuple[pd.DataFrame, set]:
    """Final match groups: one MODIS detection + its VIIRS detections.

    Each VIIRS detection is given to ONE MODIS only (the closest, then the nearest
    in time), so no VIIRS is counted in two groups. Then each group keeps at most
    cfg.matching.max_viirs_per_modis VIIRS (the closest ones).
    """
    if candidates.empty:
        return pd.DataFrame(columns=MATCHED_COLS), set()

    max_v = cfg.matching.max_viirs_per_modis

    # satellite + daynight lookup from the obs DataFrame
    meta = (obs[['observation_id', 'satellite', 'daynight']]
            .drop_duplicates('observation_id')
            .set_index('observation_id'))

    # one MODIS per VIIRS: keep the closest candidate pair for every VIIRS
    cand = (candidates
            .sort_values(['viirs_observation_id', 'distance_km', 'time_diff_minutes',
                          'modis_observation_id'], kind='stable')
            .drop_duplicates('viirs_observation_id', keep='first'))

    # cap per MODIS: closest VIIRS first, keep max_v
    cand = cand.sort_values(['modis_observation_id', 'distance_km', 'viirs_observation_id'],
                            kind='stable')
    cand = cand[cand.groupby('modis_observation_id').cumcount() < max_v].copy()

    cand['n_viirs_in_group'] = cand.groupby('modis_observation_id')['viirs_observation_id'].transform('size')
    cand['match_group_id'] = cand['modis_observation_id'].map(
        {m: make_match_group_id(m, config_version) for m in cand['modis_observation_id'].unique()})
    cand['modis_satellite'] = meta['satellite'].reindex(cand['modis_observation_id'].to_numpy()).to_numpy()
    cand['viirs_satellite'] = meta['satellite'].reindex(cand['viirs_observation_id'].to_numpy()).to_numpy()
    cand['daynight'] = meta['daynight'].reindex(cand['modis_observation_id'].to_numpy()).to_numpy()
    cand['method'] = 'spatiotemporal_haversine_closest'
    cand['config_version'] = config_version
    cand['dataset_version'] = dataset_version

    matched = cand[MATCHED_COLS].reset_index(drop=True)
    return matched, set(matched['modis_observation_id'])


def _merge_unmatched(
    base_unmatched: pd.DataFrame,   # from find_unmatched() - time + space reasons
    outside: pd.DataFrame,          # outside_overlap rows
    matched_ids: set,               # observation_ids that made it into matched
) -> pd.DataFrame:
    """Union of all three unmatched sources, deduplicated.
 
    Priority: no_candidate_in_time < no_candidate_in_space < outside_overlap
    (the most informative reason wins).  Any id that ended up matched is dropped.
    """
    parts = [df for df in (base_unmatched, outside) if not df.empty]
    if not parts:
        return pd.DataFrame(columns=UNMATCHED_COLS)
 
    combined = pd.concat(parts, ignore_index=True)
    _order = {'outside_overlap': 0, 'no_candidate_in_space': 1, 'no_candidate_in_time': 2}
    combined['_rank'] = combined['reason'].map(_order).fillna(99)
    combined = (combined.sort_values('_rank')
                        .drop_duplicates('observation_id', keep='first')
                        .drop(columns='_rank'))
    combined = combined[~combined['observation_id'].isin(matched_ids)]
    return combined[UNMATCHED_COLS].reset_index(drop=True)

def run_matching(
    overlap_df: pd.DataFrame,
    cfg: Phase2Config | None = None,
    dataset_version: str | None = None,
) -> MatchResult:
    cfg             = cfg or load_config()
    config_version  = cfg.config_version
    dataset_version = dataset_version or cfg.version('matching')
 
    if overlap_df.empty:
        return MatchResult(
            matched=pd.DataFrame(columns=MATCHED_COLS),
            unmatched=pd.DataFrame(columns=UNMATCHED_COLS),
            summary={'total_overlap_observations': 0, 'match_groups': 0,
                     'matched_modis': 0, 'matched_viirs': 0,
                     'unmatched_total': 0, 'unmatched_by_reason': {}},
        )
 
    # 2.4: assign overpasses, group, pair
    obs   = assign_overpasses(overlap_df, cfg)
    ovp   = build_overpass_groups(obs, cfg, dataset_version=dataset_version)
    pairs = build_overpass_pairs(ovp, cfg)
 
    # 2.5: spatial candidates + base unmatched
    candidates    = build_match_candidates(obs, pairs, cfg, dataset_version=dataset_version)
    base_unmatched = find_unmatched(obs, pairs, candidates, cfg, dataset_version=dataset_version)
 
    # 2.6: cap, group, outside_overlap
    outside = _outside_overlap_rows(obs, cfg, dataset_version)
 
    matched, matched_modis_ids = _apply_cap_and_build_groups(
        candidates, obs, cfg, config_version, dataset_version
    )
 
    all_matched_ids = (set() if matched.empty
                       else set(matched['modis_observation_id'])
                            | set(matched['viirs_observation_id']))
    unmatched = _merge_unmatched(base_unmatched, outside, all_matched_ids)

    # detections that had candidates but lost them: a MODIS whose VIIRS all went to a
    # closer MODIS, or a VIIRS cut by the per-group cap. every detection must end up
    # either matched or unmatched with a reason
    accounted = all_matched_ids | set(unmatched['observation_id'])
    lost = obs[~obs['observation_id'].isin(accounted)]
    if not lost.empty:
        reason = np.where(lost['sensor_family'] == 'MODIS',
                          'viirs_matched_to_closer_modis', 'over_group_cap')
        lost_rows = pd.DataFrame({
            'observation_id':   lost['observation_id'].to_numpy(),
            'region':           lost['region'].to_numpy(),
            'sensor_family':    lost['sensor_family'].to_numpy(),
            'satellite':        lost['satellite'].to_numpy(),
            'acq_datetime_utc': pd.to_datetime(lost['acq_datetime_utc'], utc=True).to_numpy(),
            'reason':           reason,
            'dataset_version':  dataset_version,
        })[UNMATCHED_COLS]
        unmatched = pd.concat([unmatched, lost_rows], ignore_index=True)

# summary   
    n_groups  = matched['match_group_id'].nunique() if not matched.empty else 0
    n_modis_m = matched['modis_observation_id'].nunique() if not matched.empty else 0
    n_viirs_m = matched['viirs_observation_id'].nunique() if not matched.empty else 0
    unm_counts = unmatched['reason'].value_counts().to_dict() if not unmatched.empty else {}
 
    summary: dict = {
        'total_overlap_observations': len(overlap_df),
        'match_groups':               n_groups,
        'matched_modis':              n_modis_m,
        'matched_viirs':              n_viirs_m,
        'unmatched_total':            len(unmatched),
        'unmatched_by_reason':        unm_counts,
    }
    if not matched.empty:
        summary['viirs_per_group_mean']     = round(
            matched.groupby('match_group_id')['viirs_observation_id'].count().mean(), 2)
        summary['distance_km_mean']         = round(matched['distance_km'].mean(), 3)
        summary['time_diff_minutes_mean']   = round(matched['time_diff_minutes'].mean(), 2)
 
    _print_summary(summary)
    return MatchResult(matched=matched, unmatched=unmatched, summary=summary,
                       overpasses=ovp, candidates=candidates)
 
def _print_summary(s: dict) -> None:
    print(
        f"\nMatching summary\n"
        f"  Overlap observations  : {s['total_overlap_observations']:,}\n"
        f"  Match groups          : {s['match_groups']:,}\n"
        f"  Matched MODIS         : {s['matched_modis']:,}\n"
        f"  Matched VIIRS         : {s['matched_viirs']:,}\n"
        f"  Unmatched total       : {s['unmatched_total']:,}\n"
        f"  Unmatched by reason   : {s['unmatched_by_reason']}"
    )
    if 'distance_km_mean' in s:
        print(
            f"  Mean distance (km)    : {s['distance_km_mean']}\n"
            f"  Mean time diff (min)  : {s['time_diff_minutes_mean']}\n"
            f"  Mean VIIRS per group  : {s['viirs_per_group_mean']}"
        )
  
if __name__ == '__main__':
    import argparse
    from phase2.phase2_overlap import load_overlap
 
    parser = argparse.ArgumentParser(
        description='Spatiotemporal matching of MODIS and VIIRS (Task 2.6)')
    parser.add_argument('--region', default=None)
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()
 
    _cfg = load_config(demo_mode=True) if args.demo else load_config()
    _overlap = load_overlap(args.region, cfg=_cfg)
    result   = run_matching(_overlap, _cfg)

    from phase2.phase2_database import store
    store(result.overpasses, 'overpass_groups', demo=args.demo)
    store(result.candidates, 'match_candidates', demo=args.demo)
    store(result.matched, 'matched_observations', demo=args.demo)
    store(result.unmatched, 'unmatched_observations', demo=args.demo)
    print(f'\nmatched sample:\n'
          f'{result.matched[["match_group_id","modis_observation_id","viirs_observation_id","distance_km"]].head(5).to_string()}')
