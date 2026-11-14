from __future__ import annotations
from phase1_modis import standardize_core

VIIRS_FIELD_MAP = {'latitude': 'latitude', 'longitude': 'longitude','bright_ti4': 'mid_ir_bt_k', 'bright_ti5': 'longwave_bt_k','frp': 'frp_mw', 'scan': 'scan_km', 'track': 'track_km',}
VIIRS_PLATFORMS = {'N': 'S-NPP', 'S-NPP': 'S-NPP', 'SUOMI-NPP': 'S-NPP', 'SUOMI NPP': 'S-NPP','N20': 'NOAA-20', 'NOAA-20': 'NOAA-20','N21': 'NOAA-21', 'NOAA-21': 'NOAA-21',}
VIIRS_CONFIDENCE = {'l': 'low', 'n': 'nominal', 'h': 'high'}


def standardize_viirs(df, source_dataset='VIIRS_SNPP_SP', version=None,
                      source_file=None, include_source_record=True):
    return standardize_core(
        df, sensor_family='VIIRS', source_dataset=source_dataset,
        thermal_fields=('bright_ti4', 'bright_ti5'),
        channel_labels=('I4', 'I5'), platform_aliases=VIIRS_PLATFORMS,
        version=version, source_file=source_file,
        include_source_record=include_source_record,
    )

