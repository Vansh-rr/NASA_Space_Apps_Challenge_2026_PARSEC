from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pandas as pd
from phase1_sources import SOURCES

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ['PARSEC_DATA_DIR']).expanduser().resolve() if os.environ.get('PARSEC_DATA_DIR') else ROOT / 'data'
FOLDERS = {'raw_modis': DATA_DIR / 'raw' / 'modis','raw_viirs': DATA_DIR / 'raw' / 'viirs','standardized': DATA_DIR / 'standardized','derived': DATA_DIR / 'derived','sample': DATA_DIR / 'sample','logs': DATA_DIR / 'logs',}

# This is creating folders as defined earliers
def make_folders() -> None:
    for folder in FOLDERS.values():
        folder.mkdir(parents=True, exist_ok=True)


def raw_folder(source: str) -> Path:
    try:
        return FOLDERS['raw_' + SOURCES[source]]
    except KeyError:
        raise ValueError(f'Unknown FIRMS source: {source!r}') from None


def raw_file_name(source, bbox, start, end):
    if source not in SOURCES:
        raise ValueError(f'Unknown FIRMS source: {source!r}')
    bounds = '_'.join(f'{float(v):g}' for v in bbox)
    return f'{source}_{bounds}_{start}_{end}.csv'

# Basically making A CSV file
def save_metadata(csv_path, source, bbox, start, end, rows):
    csv_path = Path(csv_path)
    metadata = {'source': source,'provider': 'NASA FIRMS area CSV API','bbox_west_south_east_north': list(bbox),'start_date': str(start), 'end_date': str(end), 'rows': int(rows),'downloaded_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),}
    target = csv_path.with_suffix('.json')
    temporary = target.with_name(target.name + '.tmp')
    try:
        temporary.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target

# Function for creating sample csv file; here n is mutable as per the requirement
def make_sample(csv_path, n=200):
    if n < 1:
        raise ValueError('Sample size must be positive')
    make_folders()
    df = pd.read_csv(csv_path)
    sample = df.sample(n=min(n, len(df)), random_state=42) if len(df) else df
    destination = FOLDERS['sample'] / ('sample_' + Path(csv_path).name)
    sample.to_csv(destination, index=False)
    return destination

