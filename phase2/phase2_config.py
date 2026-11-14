from __future__ import annotations
from datetime import date
from functools import lru_cache
import math
import os
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from phase1_sources import SOURCES
from phase1_storage import DATA_DIR, ROOT

CONFIG_PATH = Path(os.environ.get('PARSEC_PHASE2_CONFIG', ROOT / 'configs' / 'phase2.yaml'))
PHASE2_DIR = DATA_DIR / 'phase2'
DEMO_DIR = DATA_DIR / 'demo' / 'phase2'

SATELLITES = ('Terra', 'Aqua', 'S-NPP', 'NOAA-20', 'NOAA-21')
TimeWindow = Literal['day', '8day', 'month']


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Region(_Strict):
    name: str
    bbox: tuple[float, float, float, float]

    @field_validator('bbox')
    @classmethod
    def check_bbox(cls, bbox):
        west, south, east, north = bbox
        if not all(map(math.isfinite, bbox)):
            raise ValueError('bbox values must be finite')
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError('bbox must be [west, south, east, north] and not cross the antimeridian')
        return bbox


class Period(_Strict):
    start: date
    end: date | None = None

    @model_validator(mode='after')
    def check_order(self):
        if self.end is not None and self.start > self.end:
            raise ValueError('period start is after end')
        return self


class Dataset(_Strict):
    sensor_family: Literal['MODIS', 'VIIRS']
    satellites: list[str]

    @field_validator('satellites')
    @classmethod
    def known_satellites(cls, value):
        unknown = set(value) - set(SATELLITES)
        if unknown:
            raise ValueError(f'unknown satellites: {sorted(unknown)}')
        return value


class Grid(_Strict):
    cell_sizes_km: list[float]
    default_cell_size_km: float
    crs: str

    @model_validator(mode='after')
    def default_in_list(self):
        if any(size <= 0 for size in self.cell_sizes_km):
            raise ValueError('cell sizes must be positive')
        if self.default_cell_size_km not in self.cell_sizes_km:
            raise ValueError('default_cell_size_km must be one of cell_sizes_km')
        return self


class Matching(_Strict):
    max_time_diff_minutes: float = Field(gt=0)
    max_distance_km: float = Field(ge=0)
    use_footprint: bool
    max_viirs_per_modis: int = Field(ge=1)
    require_same_daynight: bool
    overpass_gap_minutes: float = Field(gt=0)


class FireEvents(_Strict):
    method: Literal['space_time_components'] = 'space_time_components'
    eps_km: float = Field(default=2.0, gt=0)
    eps_hours: float = Field(default=24.0, gt=0)
    min_detections: int = Field(default=1, ge=1)


class Model(_Strict):
    default_model: str
    target: str
    uncertainty_level: float = Field(gt=0, lt=1)


class Splits(_Strict):
    names: list[str]
    fractions: list[float] = [0.7, 0.15, 0.15]
    methods: list[str]
    default_method: str = 'event'
    block_deg: float = Field(default=1.0, gt=0)
    seed: int

    @model_validator(mode='after')
    def check_fractions(self):
        if len(self.fractions) != len(self.names):
            raise ValueError('splits.fractions needs one value per split name')
        if any(f < 0 for f in self.fractions) or abs(sum(self.fractions) - 1) > 1e-6:
            raise ValueError('splits.fractions must be >= 0 and add up to 1')
        if self.default_method not in self.methods:
            raise ValueError('splits.default_method must be one of splits.methods')
        return self

class Phase2Config(_Strict):
    config_version: str
    regions: dict[str, Region]
    default_region: str
    study_period: Period
    datasets: dict[str, Dataset]
    sensor_availability: dict[str, Period]
    overlap_period: Period
    grid: Grid
    time_windows: list[TimeWindow]
    default_time_window: TimeWindow
    matching: Matching
    fire_events: FireEvents = FireEvents()
    model: Model
    splits: Splits
    dataset_versions: dict[str, str]
    demo_mode: bool = False

    @model_validator(mode='after')
    def cross_checks(self):
        if self.default_region not in self.regions:
            raise ValueError(f'default_region {self.default_region!r} is not in regions')
        unknown = set(self.datasets) - set(SOURCES)
        if unknown:
            raise ValueError(f'datasets not supported by Phase 1: {sorted(unknown)}')
        for ds in self.datasets.values():
            missing = set(ds.satellites) - set(self.sensor_availability)
            if missing:
                raise ValueError(f'no sensor_availability for {sorted(missing)}')
        if self.default_time_window not in self.time_windows:
            raise ValueError('default_time_window must be one of time_windows')
        return self

    # helpers

    def region(self, name=None) -> Region:
        name = name or self.default_region
        try:
            return self.regions[name]
        except KeyError:
            raise ValueError(f'unknown region {name!r}, use one of {list(self.regions)}') from None

    def version(self, product: str) -> str:
        try:
            return f'{self.dataset_versions[product]}+cfg{self.config_version}'
        except KeyError:
            raise ValueError(f'no dataset version for {product!r}') from None

    def satellites_for(self, sensor_family: str) -> list[str]:
        return [sat for ds in self.datasets.values() if ds.sensor_family == sensor_family
                for sat in ds.satellites]

    def output_dir(self, *parts) -> Path:
        # demo output never mixes with real NASA-derived output
        base = DEMO_DIR if self.demo_mode else PHASE2_DIR
        folder = base.joinpath(*parts)
        folder.mkdir(parents=True, exist_ok=True)
        return folder


def load_config(path=None, **overrides) -> Phase2Config:
    """Read configs/phase2.yaml; overrides replace top-level keys (e.g. demo_mode=True)."""
    path = Path(path) if path is not None else CONFIG_PATH
    if not path.is_file():
        raise FileNotFoundError(f'Phase 2 config not found: {path}')
    with path.open(encoding='utf-8') as f:
        raw = yaml.safe_load(f) or {}
    raw.update(overrides)
    return Phase2Config.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> Phase2Config:
    """Cached default config for normal use."""
    return load_config()


if __name__ == '__main__':
    cfg = load_config()
    print(f'Phase 2 config {cfg.config_version} OK')
    print('regions:', ', '.join(f'{k} {v.bbox}' for k, v in cfg.regions.items()))
    print('study period:', cfg.study_period.start, '->', cfg.study_period.end)
    print('overlap from:', cfg.overlap_period.start)
    print('matching:', cfg.matching.model_dump())
    print('output folder:', cfg.output_dir())
