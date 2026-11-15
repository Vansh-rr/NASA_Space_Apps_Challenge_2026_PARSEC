from __future__ import annotations
from phase1_database import connect_db


def _where_clause(bbox=None, start=None, end=None, sensor=None):
    conditions, params = [], []
    if bbox is not None:
        from phase1_downloader import validate_bbox
        west, south, east, north = validate_bbox(bbox)
        conditions += ['longitude BETWEEN ? AND ?', 'latitude BETWEEN ? AND ?']
        params += [west, east, south, north]
    if start is not None:
        conditions.append('acq_datetime_utc >= CAST(? AS DATE)')
        params.append(str(start))
    if end is not None:
        conditions.append("acq_datetime_utc < CAST(? AS DATE) + INTERVAL '1 day'")
        params.append(str(end))
    if sensor is not None:
        if sensor not in ('MODIS', 'VIIRS'):
            raise ValueError("sensor must be 'MODIS' or 'VIIRS'")
        conditions.append('sensor_family = ?')
        params.append(sensor)
    return (' WHERE ' + ' AND '.join(conditions) if conditions else ''), params


def get_fires(bbox=None, start=None, end=None, sensor=None, limit=None, db_path=None):
    """Fetch matching observations (excludes large source_record JSON)."""
    where, params = _where_clause(bbox, start, end, sensor)
    sql = ('SELECT * EXCLUDE (source_record) FROM observations' + where
           + ' ORDER BY acq_datetime_utc')
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError('limit must be a positive integer')
        sql += ' LIMIT ?'
        params.append(limit)
    with connect_db(db_path) as con:
        return con.execute(sql, params).df()


def activity(period='day', bbox=None, start=None, end=None, sensor=None,
             db_path=None):
    """Observation count, summed and mean reported FRP by sensor/time period.

    Sum of FRP over separate overpasses is not fire energy.
    """
    if period not in ('day', 'month'):
        raise ValueError("period must be 'day' or 'month'")
    where, params = _where_clause(bbox, start, end, sensor)
    sql = f'''
        SELECT CAST(DATE_TRUNC('{period}', acq_datetime_utc) AS DATE) AS period_start,
               sensor_family,
               COUNT(*) AS detections,
               SUM(frp_mw) AS sum_observed_frp_mw,
               AVG(frp_mw) AS mean_observed_frp_mw
        FROM observations {where}
        GROUP BY 1, 2 ORDER BY 1, 2
    '''
    with connect_db(db_path) as con:
        return con.execute(sql, params).df()
