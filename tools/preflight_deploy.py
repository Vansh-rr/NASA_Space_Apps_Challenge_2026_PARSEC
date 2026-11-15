"""Check a self-contained production DuckDB snapshot without changing it."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check_snapshot(path, *, region='british_columbia', month='2023-07', allow_synthetic=False):
    import duckdb
    from phase2.phase2_config import load_config
    from phase3.api import month_range
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'Place a regular, complete database file at {path}; GitHub does not contain it.')
    if Path(str(path)+'.wal').exists():
        raise ValueError('A DuckDB WAL is present. Close writers and checkpoint a self-contained snapshot before uploading.')
    cfg = load_config()
    west, south, east, north = cfg.region(region).bbox
    start, end = month_range(month)
    with duckdb.connect(str(path), read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")
        for table in ['observations', 'model_runs', 'model_predictions', 'matched_observations',
                      'fire_calendar', 'fire_anomalies']:
            con.execute(f'SELECT * FROM {table} LIMIT 0').fetchall()
        counts = dict(con.execute('''SELECT sensor_family, COUNT(*) FROM observations
            WHERE longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?
              AND acq_datetime_utc >= CAST(? AS DATE)
              AND acq_datetime_utc < CAST(? AS DATE) + INTERVAL '1 day'
            GROUP BY sensor_family''', [west,east,south,north,start,end]).fetchall())
        if any(counts.get(s,0) == 0 for s in ['MODIS','VIIRS']):
            raise ValueError('The selected region/month needs downloaded MODIS and VIIRS observations.')
        candidates = con.execute('''SELECT r.model_run_id, r.model_name, r.is_synthetic, COUNT(*) AS n
            FROM model_runs r JOIN model_predictions p USING(model_run_id)
            JOIN (SELECT DISTINCT match_group_id FROM matched_observations
                  WHERE region = ? AND dataset_version = ?) mt ON mt.match_group_id = p.unit_id
            WHERE (? OR r.is_synthetic = FALSE)
            GROUP BY r.model_run_id,r.model_name,r.is_synthetic,r.created_at
            ORDER BY r.created_at DESC,r.model_run_id DESC''',
            [region,cfg.version('matching'),allow_synthetic]).fetchall()
        if not candidates:
            raise ValueError('No compatible real model run. Rebuild Phase 2 with the current config; a demo database cannot be published as real data.')
        run_id, model_name, synthetic, n = candidates[0]
        visible = con.execute('''SELECT COUNT(*) FROM model_predictions p
            JOIN (SELECT DISTINCT match_group_id,modis_observation_id FROM matched_observations
                  WHERE region = ? AND dataset_version = ?) mt ON mt.match_group_id=p.unit_id
            JOIN observations o ON o.observation_id=mt.modis_observation_id
            WHERE p.model_run_id=? AND o.longitude BETWEEN ? AND ? AND o.latitude BETWEEN ? AND ?
              AND o.acq_datetime_utc >= CAST(? AS DATE)
              AND o.acq_datetime_utc < CAST(? AS DATE) + INTERVAL '1 day' ''',
            [region,cfg.version('matching'),run_id,west,east,south,north,start,end]).fetchone()[0]
        if visible == 0:
            raise ValueError('The newest model run has no predictions for the frontend default month; rebuild or align the dataset before deploying.')
        bad = con.execute('''SELECT COUNT(*) FROM model_predictions WHERE model_run_id = ?
                             AND (predicted_value IS NULL OR NOT isfinite(predicted_value) OR predicted_value < 0)''', [run_id]).fetchone()[0]
        if bad:
            raise ValueError('Model predictions include missing, nonfinite or negative FRP values.')
    from phase2.model_preview import PreviewStore
    preview = PreviewStore(ROOT/'model_preview/bc-july-2023')
    return dict(database=str(path),bytes=path.stat().st_size,region=region,month=month,
                observations=counts,model_run_id=run_id,model_name=model_name,
                predictions=n,visible_predictions=visible,is_synthetic=bool(synthetic),preview_rows=preview.metadata['rows'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,default=ROOT/'data/fires.duckdb')
    p.add_argument('--region',default='british_columbia')
    p.add_argument('--month',default='2023-07')
    a=p.parse_args(argv)
    try:
        print(json.dumps(check_snapshot(a.database,region=a.region,month=a.month),indent=2))
        return 0
    except Exception as exc:
        print(f'Deployment preflight failed: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
