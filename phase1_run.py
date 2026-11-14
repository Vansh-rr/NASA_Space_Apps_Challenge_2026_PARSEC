from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
from phase1_schema import CommonObservation, OBSERVATION_COLUMNS
from phase1_storage import ROOT, DATA_DIR, make_folders
from phase1_downloader import iter_firms_chunks, split_dates, validate_bbox
from phase1_modis import standardize_modis
from phase1_viirs import standardize_viirs
from phase1_database import DB_PATH, DEMO_DB_PATH, connect_db, load_standardized
from phase1_queries import get_fires, activity

SAMPLE_URL = ('https://firms.modaps.eosdis.nasa.gov/'
              'content/notebooks/sample_viirs_snpp_071223.csv')

def example_inputs():
    """Two artificial observations solely for demonstration/testing."""
    modis = pd.DataFrame([{
        'latitude': 53.1211, 'longitude': -122.5512,
        'brightness': 338.2, 'bright_t31': 301.4, 'frp': 42.7,
        'scan': 1.2, 'track': 1.1, 'acq_date': '2023-07-12',
        'acq_time': 1840, 'satellite': 'T', 'confidence': 86,
        'daynight': 'D', 'version': '6.1',
    }])
    viirs = pd.DataFrame([{
        'latitude': 53.1232, 'longitude': -122.5481,
        'bright_ti4': 341.8, 'bright_ti5': 300.1, 'frp': 18.4,
        'scan': 0.41, 'track': 0.38, 'acq_date': '2023-07-12',
        'acq_time': 1912, 'satellite': 'N', 'confidence': 'n',
        'daynight': 'D', 'version': '2.0', 'instrument': 'VIIRS',
    }])
    return modis, viirs


def to_contract(row):
    """Validate one standardized row without per-row Pydantic overhead in bulk."""
    data = {name: row[name] for name in CommonObservation.model_fields}
    if isinstance(data['source_record'], str):
        data['source_record'] = json.loads(data['source_record'])
    nullable = (
        'ingestion_batch_id', 'confidence_numeric', 'hotspot_type_raw',
        'frp_mw', 'mid_ir_bt_k', 'longwave_bt_k', 'scan_km', 'track_km',
        'confidence_raw', 'confidence_class', 'source_file',
    )
    for name in nullable:
        if pd.isna(data[name]):
            data[name] = None
    return CommonObservation.model_validate(data)


def run_demo():
    """Keep illustrative records entirely separate from the real database."""
    raw_modis, raw_viirs = example_inputs()
    modis = standardize_modis(raw_modis)
    viirs = standardize_viirs(raw_viirs)
    assert list(modis[OBSERVATION_COLUMNS]) == list(viirs[OBSERVATION_COLUMNS])
    assert len(split_dates('2023-07-01', '2023-07-31')) == 7
    assert abs(modis.iloc[0]['delta_bt_k'] - 36.8) < 1e-9
    assert abs(viirs.iloc[0]['delta_bt_k'] - 41.7) < 1e-9
    assert abs(modis.iloc[0]['pixel_area_km2'] - 1.32) < 1e-9
    assert abs(viirs.iloc[0]['pixel_area_km2'] - 0.1558) < 1e-9
    assert to_contract(modis.iloc[0]).observation_id == modis.iloc[0]['observation_id']
    assert to_contract(viirs.iloc[0]).observation_id == viirs.iloc[0]['observation_id']
    demo_dir = DATA_DIR / 'demo' / 'standardized'
    load_standardized(modis, 'illustrative_modis', db_path=DEMO_DB_PATH,
                      parquet_dir=demo_dir)
    load_standardized(viirs, 'illustrative_viirs', db_path=DEMO_DB_PATH,
                      parquet_dir=demo_dir)
    print('\nDEMONSTRATION DATA (separate database):')
    print(get_fires(start='2023-07-12', end='2023-07-12', limit=5,
                    db_path=DEMO_DB_PATH)[
        ['sensor_family', 'satellite', 'acq_datetime_utc', 'delta_bt_k', 'frp_mw']
    ].to_string(index=False))
    print(activity('day', start='2023-07-12', end='2023-07-12',
                   db_path=DEMO_DB_PATH).to_string(index=False))
    exports = ROOT / 'exports'
    exports.mkdir(parents=True, exist_ok=True)
    (exports / 'common_observation_schema.json').write_text(
        json.dumps(CommonObservation.model_json_schema(mode='serialization'), indent=2),
        encoding='utf-8',
    )
    pd.concat((modis, viirs), ignore_index=True).to_csv(
        exports / 'illustrative_standardized_records.csv', index=False
    )
    print('Demo schema and records exported to', exports)


def run_public_sample():
    """Official public sample; useful without a MAP_KEY."""
    raw = pd.read_csv(SAMPLE_URL, dtype={'version': 'string', 'satellite': 'string',
                                         'confidence': 'string'})
    print('Public VIIRS sample shape:', raw.shape)
    data = standardize_viirs(raw, source_file=SAMPLE_URL)
    load_standardized(data, 'public_viirs_sample_2023_07_12')


def run_real(bbox, start, end):
    """Download, standardize and store each independent five-day chunk."""
    bbox = validate_bbox(bbox)
    total_inserted = 0
    for source, standardize in (
        ('MODIS_SP', standardize_modis),
        ('VIIRS_SNPP_SP', standardize_viirs),
    ):
        print(f'{source}: {start} through {end}')
        for raw in iter_firms_chunks(source, bbox, start, end):
            if raw.empty:
                continue
            path = raw.attrs.get('source_file')
            if not path:
                raise RuntimeError('FIRMS chunk is missing source_file provenance')
            output = standardize(raw, source_dataset=source, source_file=path)
            total_inserted += load_standardized(output, Path(path).stem)
            del output, raw
    print(f'New real observations inserted: {total_inserted:,}')
    print(get_fires(bbox=bbox, start=start, end=end, limit=5).to_string(index=False))
    print('Monthly raw observation summary (summed FRP is NOT fire energy):')
    print(activity('month', bbox=bbox, start=start, end=end).to_string(index=False))


def clean_legacy_demo():
    """Explicit cleanup of two known synthetic IDs without touching real FIRMS files."""
    modis, viirs = example_inputs()
    ids = [
        standardize_modis(modis).iloc[0]['observation_id'],
        standardize_viirs(viirs).iloc[0]['observation_id'],
    ]
    with connect_db(DB_PATH) as con:
        before = con.execute('SELECT COUNT(*) FROM observations').fetchall()[0][0]
        con.execute(
            'DELETE FROM observations WHERE observation_id IN (?, ?) '
            'AND source_file IS NULL', ids,
        ).fetchall()
        after = con.execute('SELECT COUNT(*) FROM observations').fetchall()[0][0]
    print(f'Removed {before - after} known legacy synthetic rows')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Parsec NASA FIRMS Phase 1')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--real', action='store_true', help='Use NASA FIRMS API')
    modes.add_argument('--sample', action='store_true', help='Use public sample VIIRS CSV')
    modes.add_argument('--demo', action='store_true', help='Use isolated synthetic examples (default)')
    modes.add_argument('--clean-legacy-demo', action='store_true',
                       help='Delete only known synthetic rows from an old real DB')
    parser.add_argument('--bbox', nargs=4, type=float, default=(-139, 48, -114, 60),
                        metavar=('WEST', 'SOUTH', 'EAST', 'NORTH'))
    parser.add_argument('--start', default='2023-07-01')
    parser.add_argument('--end', default='2023-07-31')
    args = parser.parse_args(argv)
    make_folders()
    if args.clean_legacy_demo:
        clean_legacy_demo()
    elif args.real:
        run_real(tuple(args.bbox), args.start, args.end)
    elif args.sample:
        run_public_sample()
    else:
        run_demo()
    print('Phase 1 command finished.')


if __name__ == '__main__':
    main()

