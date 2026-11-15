from __future__ import annotations
from datetime import date, timedelta
import logging
import math
from pathlib import Path
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from phase1_sources import SOURCES, get_map_key
from phase1_storage import FOLDERS, make_folders, raw_folder, raw_file_name, save_metadata

API_URL = 'https://firms.modaps.eosdis.nasa.gov/api/area/csv'
MAX_DAYS = 5
CSV_DTYPES = {'version': 'string', 'satellite': 'string', 'confidence': 'string'}
EXPECTED_COLUMNS = frozenset(('latitude', 'longitude', 'acq_date', 'acq_time'))
log = logging.getLogger('parsec.firms')


def setup_logging():
    make_folders()
    if not log.handlers:
        handler = logging.FileHandler(FOLDERS['logs'] / 'downloads.log', encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def validate_bbox(bbox):
    if len(bbox) != 4:
        raise ValueError('bbox must contain west, south, east, north')
    west, south, east, north = (float(value) for value in bbox)
    if not all(map(math.isfinite, (west, south, east, north))):
        raise ValueError('bbox values must be finite')
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError('Invalid bbox (must not cross antimeridian)')
    return west, south, east, north


def split_dates(start, end):
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if start > end:
        raise ValueError('start date exceeds end date')
    chunks = []
    current = start
    while current <= end:
        last = min(current + timedelta(days=MAX_DAYS - 1), end)
        chunks.append((current, last))
        current = last + timedelta(days=1)
    return chunks


def firms_session():
    session = requests.Session()
    retries = Retry(
        total=3, backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(('GET',)),
        respect_retry_after_header=True,
    )
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session


def _read_firms_csv(path):
    try:
        df = pd.read_csv(path, dtype=CSV_DTYPES)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
        raise RuntimeError(f'Invalid FIRMS CSV: {type(exc).__name__}') from None
    if not EXPECTED_COLUMNS.issubset(df.columns):
        raise RuntimeError('Unexpected FIRMS CSV: required columns absent')
    return df

# It downloads chunk by chunk automatically
def download_chunk(source, bbox, start, end, map_key, session):
   
    if source not in SOURCES:
        raise ValueError(f'Unknown FIRMS source: {source}')
    bbox = validate_bbox(bbox)
    if not 1 <= (end - start).days + 1 <= MAX_DAYS:
        raise ValueError('One FIRMS request must span 1–5 days')
    folder = raw_folder(source)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / raw_file_name(source, bbox, start, end)
    if path.exists():
        df = _read_firms_csv(path)
        df.attrs['source_file'] = str(path)
        log.info('Cache hit %s', path.name)
        return df

    if not map_key:
        raise RuntimeError('FIRMS_MAP_KEY is required for an uncached download')
    area = ','.join(f'{x:g}' for x in bbox)
    url = f'{API_URL}/{map_key}/{source}/{area}/{(end-start).days+1}/{start}'
    log.info('Requesting %s bbox=%s dates=%s..%s', source, area, start, end)
    try:
        response = session.get(url, timeout=(15, 120), stream=True)
    except requests.RequestException as exc:
        raise RuntimeError(f'FIRMS request failed ({type(exc).__name__})') from None
    try:
        if response.status_code != 200:
            raise RuntimeError(f'FIRMS HTTP {response.status_code} for {source}, {start}..{end}')
        temp_path = path.with_name(path.name + '.part')
        try:
            with temp_path.open('wb') as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        stream.write(chunk)
            df = _read_firms_csv(temp_path)
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)
    except requests.RequestException as exc:
        raise RuntimeError(f'FIRMS response transfer failed ({type(exc).__name__})') from None
    finally:
        response.close()

    save_metadata(path, source, bbox, start, end, len(df))
    df.attrs['source_file'] = str(path)
    log.info('Saved %s with %d rows', path.name, len(df))
    return df

# result is individually cached , at most five days
def iter_firms_chunks(source, bbox, start, end, map_key=None):

    if source not in SOURCES:
        raise ValueError(f'Unknown FIRMS source: {source!r}')
    bbox = validate_bbox(bbox)
    chunks = split_dates(start, end)
    setup_logging()
    key = map_key
    with firms_session() as session:
        for chunk_start, chunk_end in chunks:
            path = raw_folder(source) / raw_file_name(source, bbox, chunk_start, chunk_end)
            if not path.exists() and not key:
                key = get_map_key()
            df = download_chunk(source, bbox, chunk_start, chunk_end, key, session)
            df.attrs['chunk_start'] = str(chunk_start)
            df.attrs['chunk_end'] = str(chunk_end)
            yield df


def download_firms(source, bbox, start, end, map_key=None):
    chunks = [df for df in iter_firms_chunks(source, bbox, start, end, map_key)
              if not df.empty]
    if not chunks:
        return pd.DataFrame()
    combined = pd.concat(chunks, ignore_index=True).drop_duplicates(ignore_index=True)
    path = raw_folder(source) / ('combined_' + raw_file_name(source, bbox, start, end))
    
    combined.to_csv(path, index=False)
    save_metadata(path, source, bbox, start, end, len(combined))
    combined.attrs['source_file'] = str(path)
    return combined
