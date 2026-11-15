from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence
import netCDF4
import numpy as np
import pandas as pd

from phase1_storage import DATA_DIR
from phase2 import phase2_config
from phase2.phase2_config import Phase2Config
from phase2 import phase2_coverage
from phase2 import phase2_database
from phase2 import phase2_grid
from phase2 import phase2_schema

DEFAULT_COVERAGE_DIR = DATA_DIR / 'raw' / 'coverage'

FIREMASK_TO_STATE: dict[int, str] = {
    0: 'unavailable',
    1: 'unavailable',
    2: 'unavailable',
    3: 'observed',
    4: 'cloudy',
    5: 'observed',
    6: 'unknown',
    7: 'observed',
    8: 'observed',
    9: 'observed',
}
NO_DATA_VALUE = -999
PRODUCTS: dict[str, dict[str, str]] = {
    'VNP14A1': {'satellite': 'S-NPP', 'time_window': 'day'},
    'MOD14A2': {'satellite': 'Terra', 'time_window': '8day'},
    'MYD14A2': {'satellite': 'Aqua', 'time_window': '8day'},
}
MIN_PIXELS_PER_CELL = 10

_REQUIRED_VARS = ('time', 'lat', 'lon', 'FireMask')
_VALID_MASK_VALUES = frozenset((*FIREMASK_TO_STATE.keys(), NO_DATA_VALUE))
_COVERAGE_COLUMNS = phase2_schema.columns_of('observation_coverage')


def read_firemask(path: str | Path) -> dict:
    """Read raw FireMask and coordinate variables from a NASA AppEEARS NetCDF-4 file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f'NetCDF file not found: {file_path}')
    try:
        ds = netCDF4.Dataset(file_path, 'r')
    except Exception as exc:
        raise ValueError(f'Failed to open NetCDF file {file_path}: {exc}') from exc

    with ds:
        ds.set_auto_maskandscale(False)
        missing_vars = [v for v in _REQUIRED_VARS if v not in ds.variables]
        if missing_vars:
            raise ValueError(f'Missing required NetCDF variables: {missing_vars}')

        title = getattr(ds, 'title', '')
        head = str(title).split()[0] if title else ''
        if '.' not in head:
            raise ValueError(f'Cannot parse product.version from title {title!r}')
        product, version = head.split('.', 1)
        if product not in PRODUCTS:
            raise ValueError(f'Unsupported product {product!r}; expected one of {sorted(PRODUCTS)}')

        t_var = ds.variables['time']
        units = getattr(t_var, 'units', None)
        if not units:
            raise ValueError('time variable is missing units attribute')
        calendar = getattr(t_var, 'calendar', 'standard')
        raw_dates = netCDF4.num2date(t_var[:], units=units, calendar=calendar)
        dates = [date(int(d.year), int(d.month), int(d.day)) for d in np.ravel(raw_dates)]

        lat = np.asarray(ds.variables['lat'][:], dtype=float)
        lon = np.asarray(ds.variables['lon'][:], dtype=float)
        mask = np.asarray(ds.variables['FireMask'][:], dtype=int)

    unique_vals = set(np.unique(mask).tolist())
    bad_vals = sorted(unique_vals - _VALID_MASK_VALUES)
    if bad_vals:
        raise ValueError(f'FireMask contains invalid class values: {bad_vals}')

    return {
        'product': product,
        'version': version,
        'dates': dates,
        'lat': lat,
        'lon': lon,
        'mask': mask,
    }


def firemask_to_coverage(
    mask: np.ndarray,
    dates: Sequence[date],
    cell_ids: Sequence[str] | np.ndarray,
    satellite: str,
    time_window: str,
    source: str,
    dataset_version: str,
    min_pixels: int = MIN_PIXELS_PER_CELL,
) -> pd.DataFrame:
    """Aggregate pixel-level FireMask classes into per-cell observation_coverage rows."""
    mask_arr = np.asarray(mask, dtype=int)
    cells_arr = np.asarray(cell_ids, dtype=object)
    if len(dates) != mask_arr.shape[0]:
        raise ValueError('dates length must match mask time dimension')

    unique_vals = set(np.unique(mask_arr).tolist())
    bad_vals = sorted(unique_vals - _VALID_MASK_VALUES)
    if bad_vals:
        raise ValueError(f'mask contains unknown FireMask class(es): {bad_vals}')

    frames: list[pd.DataFrame] = []
    for dt, slice_2d in zip(dates, mask_arr):
        flat = slice_2d.ravel()
        if flat.shape[0] != cells_arr.shape[0]:
            raise ValueError('cell_ids length must match number of pixels in a date slice')
        valid = flat != NO_DATA_VALUE
        if not np.any(valid):
            continue
        df = pd.DataFrame({
            'cell_id': cells_arr[valid],
            'state': pd.Series(flat[valid]).map(FIREMASK_TO_STATE).to_numpy(),
        })
        totals = df.groupby('cell_id', sort=False).size()
        keep_cells = totals[totals >= min_pixels].index
        if len(keep_cells) == 0:
            continue
        df = df[df['cell_id'].isin(keep_cells)]
        state_counts = df.groupby(['cell_id', 'state'], as_index=False, sort=False).size()
        state_counts['fraction'] = (
            state_counts['size'].to_numpy(dtype=float)
            / state_counts['cell_id'].map(totals).to_numpy(dtype=float)
        )
        state_counts['satellite'] = satellite
        state_counts['window_start'] = pd.to_datetime(dt).date()
        state_counts['time_window'] = time_window
        state_counts['source'] = source
        state_counts['dataset_version'] = dataset_version
        frames.append(state_counts[_COVERAGE_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=_COVERAGE_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def pixel_cell_ids(
    lat: Sequence[float] | np.ndarray,
    lon: Sequence[float] | np.ndarray,
    grid_config: phase2_grid.GridConfig,
    cell_size_km: float,
) -> np.ndarray:
    """Assign each (lat, lon) grid pixel to a deterministic grid cell_id in row-major order."""
    lon_grid, lat_grid = np.meshgrid(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    flat_lat = lat_grid.ravel()
    flat_lon = lon_grid.ravel()
    df = pd.DataFrame({
        'observation_id': np.arange(flat_lat.size, dtype=np.int64).astype(str),
        'latitude': flat_lat,
        'longitude': flat_lon,
        'sensor_family': 'GRID',
        'satellite': 'GRID',
    })
    assigned = phase2_grid.assign_cells(df, grid_config, cell_size_km)
    return assigned['cell_id'].to_numpy()


def import_coverage_file(
    path: str | Path,
    grid_config: phase2_grid.GridConfig,
    cell_size_km: float,
    cfg: Phase2Config | None = None,
) -> pd.DataFrame:
    """Read a NASA FireMask NetCDF file and return validated observation_coverage rows."""
    info = read_firemask(path)
    prod_meta = PRODUCTS[info['product']]
    cell_ids = pixel_cell_ids(info['lat'], info['lon'], grid_config, cell_size_km)
    cov = firemask_to_coverage(
        mask=info['mask'],
        dates=info['dates'],
        cell_ids=cell_ids,
        satellite=prod_meta['satellite'],
        time_window=prod_meta['time_window'],
        source=f"{info['product']}.{info['version']}",
        dataset_version=phase2_coverage.coverage_version(cfg),
    )
    phase2_coverage.validate_coverage(cov)
    return cov


def find_coverage_files(directory: str | Path | None = None) -> list[Path]:
    """Return sorted list of *.nc files in directory (default DEFAULT_COVERAGE_DIR)."""
    folder = Path(DEFAULT_COVERAGE_DIR if directory is None else directory)
    if not folder.is_dir():
        raise ValueError(
            f'Coverage directory not found: {folder}. See docs/phase2_coverage.md.'
        )
    files = sorted(folder.glob('*.nc'))
    if not files:
        raise ValueError(
            f'No .nc files found in {folder}. See docs/phase2_coverage.md.'
        )
    return files


def run_coverage_import(
    directory: str | Path | None = None,
    region: str | None = None,
    cell_size_km: float | None = None,
    db_path: str | Path | None = None,
    demo: bool = False,
    store: bool = True,
    cfg: Phase2Config | None = None,
) -> pd.DataFrame:
    """Import all coverage NetCDF files in a directory, validate, and optionally store in DuckDB."""
    cfg = cfg or phase2_config.get_config()
    region = region if region is not None else cfg.default_region
    cell_size_km = float(
        cell_size_km if cell_size_km is not None else cfg.grid.default_cell_size_km
    )
    grid_config = phase2_grid.grid_config_from_team(region, cfg)

    files = find_coverage_files(directory)
    frames = [import_coverage_file(f, grid_config, cell_size_km, cfg) for f in files]
    rows = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=_COVERAGE_COLUMNS)
    )
    phase2_coverage.validate_coverage(rows)
    if store:
        phase2_database.store(rows, 'observation_coverage', db_path, demo)

    summary = (
        rows.groupby(['satellite', 'time_window', 'state'], as_index=False)
        .size()
        .rename(columns={'size': 'rows'})
    )
    print(summary.to_string(index=False))
    return rows


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Import NASA FireMask coverage into observation_coverage (Task 2.8)'
    )
    parser.add_argument('--dir', default=None)
    parser.add_argument('--region', default=None)
    parser.add_argument('--cell-size-km', type=float, default=None)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--no-store', action='store_true')
    args = parser.parse_args()

    run_coverage_import(
        directory=args.dir,
        region=args.region,
        cell_size_km=args.cell_size_km,
        demo=args.demo,
        store=not args.no_store,
    )