from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_schema import columns_of

CANDIDATE_COLS = columns_of('match_candidates')
UNMATCHED_COLS = columns_of('unmatched_observations')

# Haversine distance
_R_KM = 6_371.0  # mean Earth radius


def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorised Haversine distance in km.  All inputs in degrees; arrays or scalars."""
    lat1, lon1, lat2, lon2 = (np.deg2rad(np.asarray(x, dtype=float))
                              for x in (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * _R_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _xyz_km(lat, lon):
    """Points on a sphere in km, so a KD-tree can search by (chord) distance."""
    lat, lon = np.deg2rad(np.asarray(lat, float)), np.deg2rad(np.asarray(lon, float))
    return _R_KM * np.column_stack([np.cos(lat) * np.cos(lon),
                                    np.cos(lat) * np.sin(lon), np.sin(lat)])


# distance-limit helper
def _distance_limits(base_km: float, use_footprint: bool,
                     modis_pixel_areas: np.ndarray) -> np.ndarray:
    """Per-MODIS-detection distance limit (km): base + half the pixel size."""
    limits = np.full(len(modis_pixel_areas), base_km, dtype=float)
    if use_footprint:
        areas = np.asarray(modis_pixel_areas, dtype=float)
        valid = np.isfinite(areas) & (areas > 0)
        limits[valid] += 0.5 * np.sqrt(areas[valid])
    return limits


def build_match_candidates(
    obs: pd.DataFrame,
    pairs: pd.DataFrame,
    cfg: Phase2Config | None = None,
    dataset_version: str | None = None,
) -> pd.DataFrame:
    """All MODIS-VIIRS detection pairs close enough in space AND time.

    obs    output of phase2_temporal.assign_overpasses() (needs overpass_id,
           latitude, longitude, pixel_area_km2, acq_datetime_utc)
    pairs  output of phase2_temporal.build_overpass_pairs()

    Works one overpass pair at a time with a KD-tree, so memory stays small.
    One MODIS detection can get several VIIRS candidates (one-to-many) and a
    VIIRS detection can appear for several MODIS ones; task 2.6 decides.
    """
    cfg = cfg or load_config()
    m_cfg = cfg.matching
    dataset_version = dataset_version or cfg.version('matching')
    if obs.empty or pairs.empty:
        return pd.DataFrame(columns=CANDIDATE_COLS)

    cols = ['observation_id', 'latitude', 'longitude', 'pixel_area_km2', 'acq_datetime_utc']
    by_overpass = {k: g[cols] for k, g in obs.groupby('overpass_id', sort=False)}
    max_dt = pd.Timedelta(minutes=m_cfg.max_time_diff_minutes)

    chunks = []
    for pair in pairs.itertuples(index=False):
        m = by_overpass.get(pair.modis_overpass_id)
        v = by_overpass.get(pair.viirs_overpass_id)
        if m is None or v is None or m.empty or v.empty:
            continue

        limits = _distance_limits(m_cfg.max_distance_km, m_cfg.use_footprint,
                                  m['pixel_area_km2'].to_numpy())
        tree = cKDTree(_xyz_km(v['latitude'], v['longitude']))
        hits = tree.query_ball_point(_xyz_km(m['latitude'], m['longitude']), r=limits)
        counts = np.fromiter((len(h) for h in hits), dtype=int, count=len(hits))
        if counts.sum() == 0:
            continue
        mi = np.repeat(np.arange(len(m)), counts)
        vi = np.concatenate([np.asarray(h, dtype=int) for h in hits if h])

        dist = haversine_km(m['latitude'].to_numpy()[mi], m['longitude'].to_numpy()[mi],
                            v['latitude'].to_numpy()[vi], v['longitude'].to_numpy()[vi])
        dt = (v['acq_datetime_utc'].to_numpy()[vi] - m['acq_datetime_utc'].to_numpy()[mi])
        dt_min = np.abs(dt / np.timedelta64(1, 'm')).astype(float)
        keep = (dist <= limits[mi]) & (dt_min <= max_dt / pd.Timedelta(minutes=1))
        if not keep.any():
            continue

        chunks.append(pd.DataFrame({
            'modis_observation_id': m['observation_id'].to_numpy()[mi][keep],
            'viirs_observation_id': v['observation_id'].to_numpy()[vi][keep],
            'region': pair.region,
            'distance_km': dist[keep],
            'distance_limit_km': limits[mi][keep],
            'time_diff_minutes': dt_min[keep],
            'modis_overpass_id': pair.modis_overpass_id,
            'viirs_overpass_id': pair.viirs_overpass_id,
            'dataset_version': dataset_version,
        }))

    if not chunks:
        return pd.DataFrame(columns=CANDIDATE_COLS)
    out = pd.concat(chunks, ignore_index=True)
    out = out.drop_duplicates(['modis_observation_id', 'viirs_observation_id', 'region'])
    return out[CANDIDATE_COLS].reset_index(drop=True)


def find_unmatched(
    obs: pd.DataFrame,
    pairs: pd.DataFrame,
    candidates: pd.DataFrame,
    cfg: Phase2Config | None = None,
    dataset_version: str | None = None,
) -> pd.DataFrame:
    """Detections with no partner, with a reason (vectorised, no per-row loops).

    no_candidate_in_time   its overpass has no partner overpass within the time limit
    no_candidate_in_space  its overpass has a partner, but nothing close enough
    """
    cfg = cfg or load_config()
    dataset_version = dataset_version or cfg.version('matching')
    if obs.empty:
        return pd.DataFrame(columns=UNMATCHED_COLS)

    paired_overpasses = set(pairs['modis_overpass_id']) | set(pairs['viirs_overpass_id'])
    matched_ids = (set(candidates['modis_observation_id'])
                   | set(candidates['viirs_observation_id']))

    out = obs.loc[~obs['observation_id'].isin(matched_ids),
                  ['observation_id', 'region', 'sensor_family', 'satellite',
                   'acq_datetime_utc', 'overpass_id']].copy()
    out['reason'] = np.where(out['overpass_id'].isin(paired_overpasses),
                             'no_candidate_in_space', 'no_candidate_in_time')
    out['dataset_version'] = dataset_version
    return out[UNMATCHED_COLS].reset_index(drop=True)


if __name__ == '__main__':
    import argparse
    from phase2.phase2_overlap import load_overlap
    from phase2.phase2_temporal import assign_overpasses, build_overpass_groups, build_overpass_pairs
    parser = argparse.ArgumentParser(description='Spatial matching of MODIS and VIIRS (Task 2.5)')
    parser.add_argument('--region', default=None)
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _cfg = load_config(demo_mode=True) if args.demo else load_config()
    _obs = assign_overpasses(load_overlap(args.region, cfg=_cfg), _cfg)
    _pairs = build_overpass_pairs(build_overpass_groups(_obs, _cfg), _cfg)
    _cand = build_match_candidates(_obs, _pairs, _cfg)
    _unm = find_unmatched(_obs, _pairs, _cand, _cfg)

    print(f'{len(_cand):,} MODIS-VIIRS candidate pairs '
          f'({_cand["modis_observation_id"].nunique():,} MODIS, '
          f'{_cand["viirs_observation_id"].nunique():,} VIIRS detections)')
    if not _cand.empty:
        print(f'distance km: median {_cand["distance_km"].median():.2f}, '
              f'max {_cand["distance_km"].max():.2f}; '
              f'time diff min: median {_cand["time_diff_minutes"].median():.1f}')
    print('unmatched:')
    print(_unm.groupby(['sensor_family', 'reason']).size().rename('detections').to_string())
