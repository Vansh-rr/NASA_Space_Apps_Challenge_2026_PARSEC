from __future__ import annotations
import json

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from phase2.phase2_config import Phase2Config, load_config
from phase2.phase2_schema import columns_of, event_id as make_event_id

EVENT_COLS = columns_of('fire_events')
MEMBER_COLS = columns_of('fire_event_observations')
_R_KM = 6_371.0

# candidate fire events from hotspot detections: NOT verified fire perimeters or burned area.
# two detections are linked when they are within eps_km in space AND within eps_hours in time.
# chains of linked detections form one event (space-time DBSCAN with min_samples=1,
# done with a KD-tree + connected components).


def _space_time_points(df: pd.DataFrame, eps_km: float, eps_hours: float) -> np.ndarray:
    lat = np.deg2rad(df['latitude'].to_numpy(float))
    lon = np.deg2rad(df['longitude'].to_numpy(float))
    t0 = df['acq_datetime_utc'].min()
    hours = (df['acq_datetime_utc'] - t0).dt.total_seconds().to_numpy() / 3600
    return np.column_stack([
        _R_KM * np.cos(lat) * np.cos(lon),
        _R_KM * np.cos(lat) * np.sin(lon),
        _R_KM * np.sin(lat),
        hours * (eps_km / eps_hours),  # time scaled to km
    ])


def cluster_labels(df: pd.DataFrame, eps_km: float, eps_hours: float) -> np.ndarray:
    """Event label (0, 1, 2, ...) for every row of df."""
    if df.empty:
        return np.array([], dtype=int)
    pts = _space_time_points(df, eps_km, eps_hours)
    # max-norm search: every coordinate (x, y, z and scaled time) within eps_km ...
    pairs = cKDTree(pts).query_pairs(r=eps_km, p=np.inf, output_type='ndarray')
    # ... then keep only pairs whose real distance in space is within eps_km too
    space = np.linalg.norm(pts[pairs[:, 0], :3] - pts[pairs[:, 1], :3], axis=1)
    pairs = pairs[space <= eps_km]
    n = len(df)
    graph = coo_matrix((np.ones(len(pairs), dtype=np.int8), (pairs[:, 0], pairs[:, 1])),
                       shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    return labels


def build_fire_events(
    obs: pd.DataFrame,
    cfg: Phase2Config | None = None,
    dataset_version: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster detections into candidate fire events.

    obs  overlap_observations DataFrame (phase2_overlap.load_overlap())
    Returns (fire_events, fire_event_observations), both in phase2_schema layout.
    """
    cfg = cfg or load_config()
    fe = cfg.fire_events
    dataset_version = dataset_version or cfg.version('events')
    if obs.empty:
        return pd.DataFrame(columns=EVENT_COLS), pd.DataFrame(columns=MEMBER_COLS)

    required = {'observation_id', 'region', 'sensor_family', 'satellite',
                'acq_datetime_utc', 'latitude', 'longitude', 'frp_mw'}
    missing = required - set(obs.columns)
    if missing:
        raise ValueError(f'observations missing columns: {sorted(missing)}')

    df = obs.drop_duplicates(['observation_id', 'region']).copy()
    df['acq_datetime_utc'] = pd.to_datetime(df['acq_datetime_utc'], utc=True)
    parameters = json.dumps({'method': fe.method, 'eps_km': fe.eps_km,
                             'eps_hours': fe.eps_hours, 'min_detections': fe.min_detections})

    events, members = [], []
    for region, part in df.groupby('region', sort=False):
        part = part.sort_values(['acq_datetime_utc', 'observation_id']).reset_index(drop=True)
        part['_label'] = cluster_labels(part, fe.eps_km, fe.eps_hours)

        g = part.groupby('_label', sort=False)
        ev = g.agg(
            first_observation_id=('observation_id', 'first'),
            first_seen_utc=('acq_datetime_utc', 'min'),
            last_seen_utc=('acq_datetime_utc', 'max'),
            centroid_lat=('latitude', 'mean'), centroid_lon=('longitude', 'mean'),
            lat_min=('latitude', 'min'), lat_max=('latitude', 'max'),
            lon_min=('longitude', 'min'), lon_max=('longitude', 'max'),
            n_detections=('observation_id', 'size'),
            frp_sum_mw=('frp_mw', 'sum'), frp_mean_mw=('frp_mw', 'mean'),
            frp_max_mw=('frp_mw', 'max'),
        )
        counts = part.pivot_table(index='_label', columns='sensor_family',
                                  values='observation_id', aggfunc='size', fill_value=0)
        ev['n_modis'] = counts.get('MODIS', 0)
        ev['n_viirs'] = counts.get('VIIRS', 0)
        ev['sensors'] = g['sensor_family'].agg(lambda s: ','.join(sorted(s.unique())))
        ev['satellites'] = g['satellite'].agg(lambda s: ','.join(sorted(s.unique())))
        ev = ev[ev['n_detections'] >= fe.min_detections]

        ev['event_id'] = [make_event_id(oid, fe.method, cfg.config_version)
                          for oid in ev['first_observation_id']]
        ev['duration_hours'] = (ev['last_seen_utc'] - ev['first_seen_utc']).dt.total_seconds() / 3600
        ev['region'] = region
        ev['method'] = fe.method
        ev['parameters'] = parameters
        ev['dataset_version'] = dataset_version
        events.append(ev.reset_index(drop=True)[EVENT_COLS])

        keep = part[part['_label'].isin(ev.index)]
        members.append(pd.DataFrame({
            'event_id': keep['_label'].map(ev['event_id']).to_numpy(),
            'observation_id': keep['observation_id'].to_numpy(),
            'region': region,
            'dataset_version': dataset_version,
        }))

    events = pd.concat(events, ignore_index=True).sort_values('first_seen_utc')
    members = pd.concat(members, ignore_index=True)
    return events.reset_index(drop=True), members[MEMBER_COLS]


if __name__ == '__main__':
    import argparse
    from phase2.phase2_database import store
    from phase2.phase2_overlap import load_overlap
    parser = argparse.ArgumentParser(description='Fire event detection (Task 2.7)')
    parser.add_argument('--region', default=None)
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()

    _cfg = load_config(demo_mode=True) if args.demo else load_config()
    _region = args.region or _cfg.default_region
    _events, _members = build_fire_events(load_overlap(_region, cfg=_cfg), _cfg)

    _out = _cfg.output_dir('events')
    _events.to_parquet(_out / f'fire_events_{_region}.parquet', index=False)
    _members.to_parquet(_out / f'fire_event_observations_{_region}.parquet', index=False)
    store(_events, 'fire_events', demo=args.demo)
    store(_members, 'fire_event_observations', demo=args.demo)

    fe = _cfg.fire_events
    print(f'{len(_members):,} detections -> {len(_events):,} candidate fire events '
          f'(eps {fe.eps_km:g} km / {fe.eps_hours:g} h)')
    sizes = _events['n_detections']
    print(f'detections per event: median {sizes.median():.0f}, max {sizes.max():,}; '
          f'single-detection events: {(sizes == 1).sum():,}')
    print(f'events seen by both sensors: {(_events["sensors"] == "MODIS,VIIRS").sum():,}')
    print('largest events:')
    top = _events.nlargest(5, 'n_detections')[
        ['first_seen_utc', 'duration_hours', 'centroid_lat', 'centroid_lon',
         'n_modis', 'n_viirs', 'frp_max_mw']]
    print(top.round({'duration_hours': 1, 'centroid_lat': 2, 'centroid_lon': 2,
                     'frp_max_mw': 1}).to_string(index=False))
