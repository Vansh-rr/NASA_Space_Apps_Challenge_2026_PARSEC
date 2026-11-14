from __future__ import annotations
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from typing import Any, Literal
from uuid import UUID
import pandas as pd
from pydantic import (AwareDatetime, BaseModel, ConfigDict, Field,computed_field, field_validator, model_validator,)

SensorFamily = Literal['MODIS', 'VIIRS']
Satellite = Literal['Terra', 'Aqua', 'S-NPP', 'NOAA-20', 'NOAA-21']
ConfidenceScheme = Literal['numeric_0_100', 'categorical_lnh']
ConfidenceClass = Literal['low', 'nominal', 'high']

# censor dependent constraints are stated global
SENSOR_RULES = {
    'MODIS': (frozenset(('Terra', 'Aqua')), 'numeric_0_100',
              ('B21/B22_unspecified', 'B31')),
    'VIIRS': (frozenset(('S-NPP', 'NOAA-20', 'NOAA-21')), 'categorical_lnh',
              ('I4', 'I5')),
}

OBSERVATION_COLUMNS = [
    'observation_id', 'schema_version', 'sensor_family', 'instrument','satellite', 'source_dataset', 'source_version', 'acq_datetime_utc','acq_date', 'daynight', 'latitude', 'longitude', 'frp_mw','mid_ir_bt_k', 'mid_ir_channel', 'longwave_bt_k', 'longwave_channel','delta_bt_k', 'scan_km', 'track_km', 'pixel_area_km2', 'confidence_raw','confidence_scheme', 'confidence_numeric', 'confidence_class','hotspot_type_raw', 'source_record', 'source_file','ingestion_batch_id', 'ingested_at',
]

# This is a uniquely generated Project id , not officially stated/published by NASA
def make_observation_id(source_dataset, source_version, sensor_family,satellite, acquisition, latitude, longitude) -> str | None:
   
    if any(pd.isna(x) for x in (acquisition, latitude, longitude, satellite)):
        return None
    stamp = pd.Timestamp(acquisition)
    if stamp.tzinfo is None:
        raise ValueError('Observation ID requires timezone-aware acquisition')
    identity = [
        str(source_dataset), str(source_version), str(sensor_family),str(satellite), stamp.tz_convert('UTC').isoformat(),float(latitude), float(longitude),
    ]
    canonical = json.dumps(identity, separators=(',', ':'), ensure_ascii=False)
    return sha256(canonical.encode('utf-8')).hexdigest()

# Common pire pixel observation , not to be confused with fire based activity/event
class CommonObservation(BaseModel):
    
    model_config = ConfigDict(extra='forbid', validate_assignment=True)

    schema_version: int = Field(default=1, ge=1)
    sensor_family: SensorFamily
    instrument: SensorFamily
    satellite: Satellite
    source_dataset: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    acq_datetime_utc: AwareDatetime
    daynight: Literal['D', 'N']
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    frp_mw: float | None = Field(..., ge=0, allow_inf_nan=False)
    mid_ir_bt_k: float | None = Field(..., gt=0, allow_inf_nan=False)
    mid_ir_channel: str = Field(min_length=1)
    longwave_bt_k: float | None = Field(..., gt=0, allow_inf_nan=False)
    longwave_channel: str = Field(min_length=1)
    scan_km: float | None = Field(..., gt=0, allow_inf_nan=False)
    track_km: float | None = Field(..., gt=0, allow_inf_nan=False)
    confidence_raw: str | None = None
    confidence_scheme: ConfidenceScheme
    confidence_numeric: int | None = Field(default=None, ge=0, le=100)
    confidence_class: ConfidenceClass | None = None
    hotspot_type_raw: int | None = None
    source_record: dict[str, Any]
    source_file: str | None = None
    ingestion_batch_id: UUID | None = None
    ingested_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator('acq_datetime_utc', 'ingested_at')
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def check_sensor_contract(self):
        if self.instrument != self.sensor_family:
            raise ValueError('instrument must match sensor_family')
        satellites, scheme, channels = SENSOR_RULES[self.sensor_family]
        is_modis = self.sensor_family == 'MODIS'
        if self.satellite not in satellites:
            raise ValueError('Invalid satellite for the selected sensor')
        if self.confidence_scheme != scheme or (
            (self.confidence_numeric is None or self.confidence_class is not None)
            if is_modis else
            (self.confidence_class is None or self.confidence_numeric is not None)
        ):
            raise ValueError('Invalid sensor-specific confidence encoding')
        if (self.mid_ir_channel, self.longwave_channel) != channels:
            raise ValueError('Invalid sensor-specific thermal channels')
        return self
# all the @ quantities are automatically computed scientific quantities
    @computed_field
    @property
    def observation_id(self) -> str:
        return make_observation_id(self.source_dataset, self.source_version, self.sensor_family,self.satellite, self.acq_datetime_utc, self.latitude, self.longitude,)

    @computed_field
    @property
    def acq_date(self) -> date:
        return self.acq_datetime_utc.date()

    @computed_field
    @property
    def delta_bt_k(self) -> float | None:
        if self.mid_ir_bt_k is None or self.longwave_bt_k is None:
            return None
        return self.mid_ir_bt_k - self.longwave_bt_k

    @computed_field
    @property
    def pixel_area_km2(self) -> float | None:
        if self.scan_km is None or self.track_km is None:
            return None
        return self.scan_km * self.track_km


assert set(OBSERVATION_COLUMNS) == (
    set(CommonObservation.model_fields) | set(CommonObservation.model_computed_fields)
), 'CommonObservation and export columns differ'

