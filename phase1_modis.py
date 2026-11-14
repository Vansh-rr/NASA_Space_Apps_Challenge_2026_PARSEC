from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
import numpy as np
import pandas as pd
from phase1_schema import OBSERVATION_COLUMNS, make_observation_id

MODIS_FIELD_MAP = {
    'latitude': 'latitude', 'longitude': 'longitude',
    'brightness': 'mid_ir_bt_k', 'bright_t31': 'longwave_bt_k',
    'frp': 'frp_mw', 'scan': 'scan_km', 'track': 'track_km',
}
MODIS_PLATFORMS = {
    'T': 'Terra', 'A': 'Aqua', 'TERRA': 'Terra', 'AQUA': 'Aqua',
}
VIIRS_CONFIDENCE = {'l': 'low', 'n': 'nominal', 'h': 'high'}


def parse_acquisition_datetime(dates, times):
    date_text = dates.astype('string').str.strip()
    time_text = (times.astype('string').str.strip()
                 .str.replace(r'\.0$', '', regex=True).str.zfill(4))
    return pd.to_datetime(date_text + ' ' + time_text,
                          format='%Y-%m-%d %H%M', errors='coerce', utc=True)


def parse_numeric(values):
    return pd.to_numeric(values, errors='coerce').replace([np.inf, -np.inf], np.nan)


def calculate_delta_bt(mid_ir, longwave):
    return mid_ir - longwave


def calculate_pixel_area(scan, track):
    """Approximate footprint area, NOT burned/fire area."""
    return scan * track


def standardize_core(df, *, sensor_family, source_dataset, thermal_fields,
                     channel_labels, platform_aliases, version=None,
                     source_file=None, include_source_record=True):
    """Vectorized transformation of one FIRMS raw DataFrame.

    Source CSVs are untouched. The returned DataFrame has the same 30 output
    fields for both sensors, plus one helper flag for the database loader.
    """
    needed = {
        'latitude', 'longitude', 'acq_date', 'acq_time', 'satellite',
        'frp', 'scan', 'track', 'confidence', 'daynight', *thermal_fields,
    }
    missing = sorted(needed - set(df.columns))
    if missing:
        raise ValueError(f'Missing {sensor_family} FIRMS columns: {missing}')
    if sensor_family not in ('MODIS', 'VIIRS'):
        raise ValueError(f'Unsupported sensor family {sensor_family!r}')
    if df.empty:
        
        return pd.DataFrame(columns=OBSERVATION_COLUMNS + ['valid_coordinates'])
    df = df.reset_index(drop=True)
    out = pd.DataFrame(index=df.index)
    out['schema_version'] = 1
    out['sensor_family'] = sensor_family
    out['instrument'] = sensor_family
    out['satellite'] = (df['satellite'].astype('string').str.strip().str.upper()
                        .map(platform_aliases))
    out['source_dataset'] = source_dataset
    out['source_version'] = (str(version) if version is not None else
                             df['version'].astype('string').fillna('unknown')
                             if 'version' in df else 'unknown')

    out['acq_datetime_utc'] = parse_acquisition_datetime(df['acq_date'], df['acq_time'])
    out['acq_date'] = out['acq_datetime_utc'].dt.date
    out['daynight'] = df['daynight'].astype('string').str.strip().str.upper()
    out['latitude'] = parse_numeric(df['latitude'])
    out['longitude'] = parse_numeric(df['longitude'])
    out['frp_mw'] = parse_numeric(df['frp'])
    out.loc[out['frp_mw'] < 0, 'frp_mw'] = np.nan
    out['mid_ir_bt_k'] = parse_numeric(df[thermal_fields[0]])
    out['longwave_bt_k'] = parse_numeric(df[thermal_fields[1]])
    for column in ('mid_ir_bt_k', 'longwave_bt_k'):
        out.loc[out[column] <= 0, column] = np.nan
    out['mid_ir_channel'] = channel_labels[0]
    out['longwave_channel'] = channel_labels[1]
    out['delta_bt_k'] = calculate_delta_bt(out['mid_ir_bt_k'], out['longwave_bt_k'])
    out['scan_km'] = parse_numeric(df['scan'])
    out['track_km'] = parse_numeric(df['track'])
    for column in ('scan_km', 'track_km'):
        out.loc[out[column] <= 0, column] = np.nan
    out['pixel_area_km2'] = calculate_pixel_area(out['scan_km'], out['track_km'])
    out['confidence_raw'] = df['confidence'].astype('string').str.strip()

    if sensor_family == 'MODIS':
        out['confidence_scheme'] = 'numeric_0_100'
        numeric_conf = parse_numeric(df['confidence'])
        numeric_conf = numeric_conf.where(numeric_conf.between(0, 100) & numeric_conf.mod(1).eq(0))
        out['confidence_numeric'] = numeric_conf.astype('Int64')
        out['confidence_class'] = pd.Series(pd.NA, index=df.index, dtype='string')
    else:
        out['confidence_scheme'] = 'categorical_lnh'
        out['confidence_numeric'] = pd.Series(pd.NA, index=df.index, dtype='Int64')
        out['confidence_class'] = (df['confidence'].astype('string').str.strip().str.lower()
                                   .map(VIIRS_CONFIDENCE).astype('string'))

    hotspot_type = parse_numeric(df['type']) if 'type' in df.columns else pd.Series(np.nan, index=df.index)
    out['hotspot_type_raw'] = hotspot_type.where(hotspot_type.mod(1).eq(0)).astype('Int64')
    out['source_file'] = str(source_file or df.attrs.get('source_file')) if (source_file or df.attrs.get('source_file')) else None
    out['ingestion_batch_id'] = str(uuid4())
    out['ingested_at'] = pd.Timestamp(datetime.now(timezone.utc))

    if include_source_record:
        
        records = df.to_json(orient='records', lines=True, date_format='iso', double_precision=15)
        out['source_record'] = records.splitlines()
    else:
        out['source_record'] = '{}'

    out['valid_coordinates'] = (
        out['latitude'].between(-90, 90) & out['longitude'].between(-180, 180)
    )
    fields = ['source_dataset', 'source_version', 'sensor_family', 'satellite',
              'acq_datetime_utc', 'latitude', 'longitude']
    out['observation_id'] = [make_observation_id(*values)
                             for values in out[fields].itertuples(index=False, name=None)]
    return out[OBSERVATION_COLUMNS + ['valid_coordinates']]


def standardize_modis(df, product=None, version=None, source_file=None,
                      include_source_record=True, source_dataset=None):
    """Support old `product=` keyword and new `source_dataset=` keyword."""
    return standardize_core(
        df, sensor_family='MODIS', source_dataset=source_dataset or product or 'MODIS_SP',
        thermal_fields=('brightness', 'bright_t31'),
        channel_labels=('B21/B22_unspecified', 'B31'),
        platform_aliases=MODIS_PLATFORMS, version=version,
        source_file=source_file, include_source_record=include_source_record,
    )

