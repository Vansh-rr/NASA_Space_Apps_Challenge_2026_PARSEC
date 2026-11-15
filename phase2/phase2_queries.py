from __future__ import annotations
import pandas as pd

from phase2.phase2_database import connect

# ready-made reads of the Phase 2 tables, for analysis and later for the API
# bbox = (west, south, east, north); dates 'YYYY-MM-DD', end date included


def _filters(alias='', bbox=None, start=None, end=None, time_col='acq_datetime_utc',
             lat_col='latitude', lon_col='longitude', region=None, dataset_version=None):
    p = f'{alias}.' if alias else ''
    cond, params = [], []
    if bbox is not None:
        west, south, east, north = map(float, bbox)
        if not (west < east and south < north):
            raise ValueError('bbox must be (west, south, east, north)')
        cond += [f'{p}{lon_col} BETWEEN ? AND ?', f'{p}{lat_col} BETWEEN ? AND ?']
        params += [west, east, south, north]
    if start is not None:
        cond.append(f'{p}{time_col} >= CAST(? AS DATE)')
        params.append(str(start))
    if end is not None:
        cond.append(f"{p}{time_col} < CAST(? AS DATE) + INTERVAL '1 day'")
        params.append(str(end))
    if region is not None:
        cond.append(f'{p}region = ?')
        params.append(region)
    if dataset_version is not None:
        cond.append(f'{p}dataset_version = ?')
        params.append(dataset_version)
    return cond, params


def _run(sql, params, tables, db_path=None, demo=False):
    with connect(db_path, demo, tables=tables) as con:
        return con.execute(sql, params).df()


def get_overlap(region=None, bbox=None, start=None, end=None, sensor=None,
                dataset_version=None, db_path=None, demo=False):
    cond, params = _filters('', bbox, start, end, region=region, dataset_version=dataset_version)
    if sensor is not None:
        cond.append('sensor_family = ?')
        params.append(sensor)
    where = ' WHERE ' + ' AND '.join(cond) if cond else ''
    return _run(f'SELECT * FROM overlap_observations{where} ORDER BY acq_datetime_utc',
                params, ['overlap_observations'], db_path, demo)


def get_matches(region=None, bbox=None, start=None, end=None, dataset_version=None,
                db_path=None, demo=False):
    """Matched pairs with both detections' position, time and FRP (from phase 1 observations)."""
    cond, params = _filters('mo', bbox, start, end)  # place/time of the MODIS detection
    extra, p2 = _filters('mt', region=region, dataset_version=dataset_version)
    where = ' WHERE ' + ' AND '.join(cond + extra) if (cond or extra) else ''
    sql = f'''
        SELECT mt.*, mo.acq_datetime_utc AS modis_time, mo.latitude AS modis_lat,
               mo.longitude AS modis_lon, mo.frp_mw AS modis_frp_mw,
               vo.acq_datetime_utc AS viirs_time, vo.latitude AS viirs_lat,
               vo.longitude AS viirs_lon, vo.frp_mw AS viirs_frp_mw
        FROM matched_observations mt
        JOIN observations mo ON mo.observation_id = mt.modis_observation_id
        JOIN observations vo ON vo.observation_id = mt.viirs_observation_id
        {where}
        ORDER BY mo.acq_datetime_utc, mt.match_group_id
    '''
    return _run(sql, params + p2, ['matched_observations'], db_path, demo)


def get_unmatched(region=None, reason=None, sensor=None, start=None, end=None,
                  dataset_version=None, db_path=None, demo=False):
    cond, params = _filters('', None, start, end, region=region, dataset_version=dataset_version)
    if reason is not None:
        cond.append('reason = ?')
        params.append(reason)
    if sensor is not None:
        cond.append('sensor_family = ?')
        params.append(sensor)
    where = ' WHERE ' + ' AND '.join(cond) if cond else ''
    return _run(f'SELECT * FROM unmatched_observations{where} ORDER BY acq_datetime_utc',
                params, ['unmatched_observations'], db_path, demo)


def get_events(region=None, bbox=None, start=None, end=None, min_detections=None,
               min_duration_hours=None, dataset_version=None, db_path=None, demo=False):
    cond, params = _filters('', bbox, start, end, time_col='first_seen_utc',
                            lat_col='centroid_lat', lon_col='centroid_lon',
                            region=region, dataset_version=dataset_version)
    if min_detections is not None:
        cond.append('n_detections >= ?')
        params.append(int(min_detections))
    if min_duration_hours is not None:
        cond.append('duration_hours >= ?')
        params.append(float(min_duration_hours))
    where = ' WHERE ' + ' AND '.join(cond) if cond else ''
    return _run(f'SELECT * FROM fire_events{where} ORDER BY first_seen_utc',
                params, ['fire_events'], db_path, demo)


def get_event_detections(event_id, dataset_version=None, db_path=None, demo=False):
    """All phase 1 detections that belong to one fire event."""
    sql = '''
        SELECT o.* EXCLUDE (source_record), e.event_id
        FROM fire_event_observations e
        JOIN observations o ON o.observation_id = e.observation_id
        WHERE e.event_id = ?
    '''
    params = [event_id]
    if dataset_version is not None:
        sql += ' AND e.dataset_version = ?'
        params.append(dataset_version)
    return _run(sql + ' ORDER BY o.acq_datetime_utc', params,
                ['fire_event_observations'], db_path, demo)


def get_grid_counts(cell_size_km=5, grid_version=None, start=None, end=None,
                    db_path=None, demo=False):
    """Detections per grid cell and sensor (needs grid_observations from task 2.3)."""
    cond, params = _filters('o', None, start, end)
    cond += ['g.cell_size_km = ?']
    params += [float(cell_size_km)]
    if grid_version is not None:
        cond.append('g.grid_version = ?')
        params.append(grid_version)
    sql = f'''
        SELECT g.cell_id, o.sensor_family, o.satellite, COUNT(*) AS detections,
               SUM(o.frp_mw) AS sum_observed_frp_mw
        FROM grid_observations g
        JOIN observations o ON o.observation_id = g.observation_id
        WHERE {' AND '.join(cond)}
        GROUP BY ALL ORDER BY detections DESC
    '''
    return _run(sql, params, ['grid_observations'], db_path, demo)