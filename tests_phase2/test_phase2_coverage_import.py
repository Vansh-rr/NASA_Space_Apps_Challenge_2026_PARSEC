from datetime import date
from pathlib import Path
import netCDF4
import numpy as np
import pandas as pd
import pytest

from phase2 import phase2_coverage
from phase2 import phase2_coverage_import
from phase2 import phase2_database
from phase2 import phase2_grid
from phase2 import phase2_schema
from phase2.phase2_coverage_import import (
    FIREMASK_TO_STATE,
    MIN_PIXELS_PER_CELL,
    NO_DATA_VALUE,
    PRODUCTS,
    firemask_to_coverage,
    import_coverage_file,
    pixel_cell_ids,
    read_firemask,
)


def _write_nc(
    path: Path,
    title: str = 'VNP14A1.002 for aid0001',
    times: list[float] | None = None,
    lats: list[float] | None = None,
    lons: list[float] | None = None,
    mask: np.ndarray | None = None,
    fill_value: int | None = None,
    include_firemask: bool = True,
) -> Path:
    times = [0.0, 86400.0] if times is None else times
    lats = [52.5, 52.6, 52.7] if lats is None else lats
    lons = [-121.5, -121.4, -121.3, -121.2] if lons is None else lons
    if mask is None:
        mask = np.full((len(times), len(lats), len(lons)), 5, dtype=np.int16)

    with netCDF4.Dataset(path, 'w', format='NETCDF4') as ds:
        ds.title = title
        ds.createDimension('time', len(times))
        ds.createDimension('lat', len(lats))
        ds.createDimension('lon', len(lons))

        t_var = ds.createVariable('time', 'f8', ('time',))
        t_var.units = 'seconds since 2000-01-01 00:00:00+00:00'
        t_var.calendar = 'julian'
        t_var[:] = times

        lat_var = ds.createVariable('lat', 'f8', ('lat',))
        lat_var[:] = lats

        lon_var = ds.createVariable('lon', 'f8', ('lon',))
        lon_var[:] = lons

        if include_firemask:
            fm_var = ds.createVariable(
                'FireMask', 'i2', ('time', 'lat', 'lon'), fill_value=fill_value
            )
            fm_var[:] = mask
    return path


def test_1_known_fractions():
    mask = np.array([[[5] * 12 + [4] * 8]], dtype=int)
    cell_ids = np.array(['c1'] * 20)
    out = firemask_to_coverage(
        mask, [date(2023, 7, 15)], cell_ids, 'S-NPP', 'day', 'VNP14A1.002', 'v1'
    )
    by_state = dict(zip(out['state'], out['fraction']))
    assert set(by_state) == {'observed', 'cloudy'}
    assert by_state['observed'] == pytest.approx(0.6)
    assert by_state['cloudy'] == pytest.approx(0.4)


def test_2_class_0_is_kept():
    mask = np.zeros((1, 4, 5), dtype=int)
    cell_ids = np.array(['c1'] * 20)
    out = firemask_to_coverage(
        mask, [date(2023, 7, 15)], cell_ids, 'S-NPP', 'day', 'VNP14A1.002', 'v1'
    )
    assert len(out) == 1
    assert out.iloc[0]['state'] == 'unavailable'
    assert out.iloc[0]['fraction'] == pytest.approx(1.0)


def test_3_fire_counts_as_observed():
    vals = [5, 5, 7, 8, 9] + [5] * 15
    mask = np.array(vals, dtype=int).reshape(1, 4, 5)
    cell_ids = np.array(['c1'] * 20)
    out = firemask_to_coverage(
        mask, [date(2023, 7, 15)], cell_ids, 'S-NPP', 'day', 'VNP14A1.002', 'v1'
    )
    assert len(out) == 1
    assert out.iloc[0]['state'] == 'observed'
    assert out.iloc[0]['fraction'] == pytest.approx(1.0)


def test_4_no_data_value_ignored():
    vals = [5] * 20 + [NO_DATA_VALUE] * 30
    mask = np.array(vals, dtype=int).reshape(1, 5, 10)
    cell_ids = np.array(['c1'] * 50)
    out = firemask_to_coverage(
        mask, [date(2023, 7, 15)], cell_ids, 'S-NPP', 'day', 'VNP14A1.002', 'v1'
    )
    assert len(out) == 1
    assert out.iloc[0]['state'] == 'observed'
    assert out.iloc[0]['fraction'] == pytest.approx(1.0)


def test_5_too_few_pixels():
    vals = [5] * 5 + [NO_DATA_VALUE] * 15
    mask = np.array(vals, dtype=int).reshape(1, 4, 5)
    cell_ids = np.array(['c1'] * 20)
    out = firemask_to_coverage(
        mask,
        [date(2023, 7, 15)],
        cell_ids,
        'S-NPP',
        'day',
        'VNP14A1.002',
        'v1',
        min_pixels=10,
    )
    assert out.empty
    assert list(out.columns) == phase2_schema.columns_of('observation_coverage')


def test_6_two_cells_two_dates():
    d0 = [5] * 10 + [4] * 10 + [3] * 15 + [6] * 5
    d1 = [0] * 20 + [5] * 10 + [4] * 10
    mask = np.array([d0, d1], dtype=int).reshape(2, 4, 10)
    cell_ids = np.array(['c1'] * 20 + ['c2'] * 20)
    dates = [date(2023, 7, 15), date(2023, 7, 16)]
    out = firemask_to_coverage(
        mask, dates, cell_ids, 'S-NPP', 'day', 'VNP14A1.002', 'v1'
    )
    sums = out.groupby(['cell_id', 'window_start'])['fraction'].sum()
    assert len(sums) == 4
    for total in sums:
        assert abs(total - 1.0) <= 1e-9


def test_7_output_schema_and_validation():
    mask = np.array([[[5] * 12 + [4] * 8]], dtype=int)
    cell_ids = np.array(['c1'] * 20)
    ver = phase2_coverage.coverage_version()
    out = firemask_to_coverage(
        mask, [date(2023, 7, 15)], cell_ids, 'S-NPP', 'day', 'VNP14A1.002', ver
    )
    assert list(out.columns) == phase2_schema.columns_of('observation_coverage')
    phase2_coverage.validate_coverage(out)


def test_8_read_firemask_round_trip(tmp_path: Path):
    expected = np.arange(24, dtype=np.int16).reshape(2, 3, 4) % 10
    nc_path = _write_nc(
        tmp_path / 'sample.nc',
        title='VNP14A1.002 for aid0001',
        times=[0.0, 86400.0],
        mask=expected,
    )
    info = read_firemask(nc_path)
    assert info['product'] == 'VNP14A1'
    assert info['version'] == '002'
    assert info['dates'] == [date(2000, 1, 1), date(2000, 1, 2)]
    assert info['mask'].shape == (2, 3, 4)
    assert np.array_equal(info['mask'], expected)


def test_9_fill_value_trap(tmp_path: Path):
    zeros_and_fives = np.zeros((1, 3, 4), dtype=np.int16)
    zeros_and_fives[0, 0, :] = 5
    nc_path = _write_nc(
        tmp_path / 'fill_zero.nc',
        times=[0.0],
        mask=zeros_and_fives,
        fill_value=0,
    )
    info = read_firemask(nc_path)
    assert not np.ma.isMaskedArray(info['mask'])
    assert (info['mask'][0, 1:, :] == 0).all()


def test_10_wrong_format(tmp_path: Path):
    with pytest.raises(ValueError):
        read_firemask(tmp_path / 'missing.nc')

    bad_nc = tmp_path / 'not_really.nc'
    bad_nc.write_text('hello world', encoding='utf-8')
    with pytest.raises(ValueError):
        read_firemask(bad_nc)

    no_fm = _write_nc(tmp_path / 'no_fm.nc', include_firemask=False)
    with pytest.raises(ValueError):
        read_firemask(no_fm)

    bad_prod = _write_nc(tmp_path / 'bad_prod.nc', title='ABC123.001 for aid0001')
    with pytest.raises(ValueError):
        read_firemask(bad_prod)

    bad_val_mask = np.full((2, 3, 4), 42, dtype=np.int16)
    bad_val = _write_nc(tmp_path / 'bad_val.nc', mask=bad_val_mask)
    with pytest.raises(ValueError):
        read_firemask(bad_val)


def test_11_time_window_from_product(tmp_path: Path):
    grid_cfg = phase2_grid.GridConfig(
        region_name='bc_dev', bbox=(-123.0, 52.0, -120.0, 54.0)
    )
    lats = [53.000, 53.001, 53.002, 53.003]
    lons = [-121.500, -121.501, -121.502, -121.503]
    mask = np.full((1, 4, 4), 5, dtype=np.int16)
    nc_path = _write_nc(
        tmp_path / 'mod14a2.nc',
        title='MOD14A2.061 for aid0001',
        times=[86400.0 * 400],
        lats=lats,
        lons=lons,
        mask=mask,
    )
    out = import_coverage_file(nc_path, grid_cfg, cell_size_km=10.0)
    assert not out.empty
    assert (out['satellite'] == 'Terra').all()
    assert (out['time_window'] == '8day').all()
    assert (out['source'] == 'MOD14A2.061').all()
    phase2_coverage.validate_coverage(out)


def test_12_pixel_order():
    grid_cfg = phase2_grid.GridConfig(
        region_name='bc_dev', bbox=(-123.0, 52.0, -120.0, 54.0)
    )
    lats = [53.5, 52.5]
    lons = [-122.5, -121.5, -120.5]
    ids = pixel_cell_ids(lats, lons, grid_cfg, 10.0)
    assert len(ids) == 6

    pts = [
        (53.5, -122.5),
        (53.5, -121.5),
        (53.5, -120.5),
        (52.5, -122.5),
        (52.5, -121.5),
        (52.5, -120.5),
    ]
    df = pd.DataFrame({
        'observation_id': [f'p{i}' for i in range(6)],
        'latitude': [p[0] for p in pts],
        'longitude': [p[1] for p in pts],
        'sensor_family': 'MODIS',
        'satellite': 'Terra',
    })
    expected = list(phase2_grid.assign_cells(df, grid_cfg, 10.0)['cell_id'])
    assert list(ids) == expected
    assert len(set(ids)) == 6


def _write_two_nc_pair(directory: Path) -> None:
    lats = [53.000, 53.001, 53.002, 53.003]
    lons = [-121.500, -121.501, -121.502, -121.503]
    mask = np.full((1, 4, 4), 5, dtype=np.int16)
    _write_nc(
        directory / 'vnp14a1.nc',
        title='VNP14A1.002 for aid0001',
        times=[86400.0 * 400],
        lats=lats,
        lons=lons,
        mask=mask,
    )
    _write_nc(
        directory / 'mod14a2.nc',
        title='MOD14A2.061 for aid0001',
        times=[86400.0 * 400],
        lats=lats,
        lons=lons,
        mask=mask,
    )


def test_13_find_coverage_files(tmp_path: Path):
    folder = tmp_path / 'cov'
    folder.mkdir()
    _write_nc(folder / 'b.nc')
    _write_nc(folder / 'a.nc')
    (folder / 'notes.txt').write_text('notes', encoding='utf-8')
    assert phase2_coverage_import.find_coverage_files(folder) == [
        folder / 'a.nc',
        folder / 'b.nc',
    ]

    empty = tmp_path / 'empty'
    empty.mkdir()
    with pytest.raises(ValueError, match='docs/phase2_coverage.md'):
        phase2_coverage_import.find_coverage_files(empty)

    with pytest.raises(ValueError, match='docs/phase2_coverage.md'):
        phase2_coverage_import.find_coverage_files(tmp_path / 'does_not_exist')


def test_14_run_coverage_import_no_store(tmp_path: Path):
    _write_two_nc_pair(tmp_path)
    out = phase2_coverage_import.run_coverage_import(
        directory=tmp_path, region='bc_dev', cell_size_km=10, store=False
    )
    assert set(out['satellite']) == {'S-NPP', 'Terra'}
    assert (out.loc[out['satellite'] == 'S-NPP', 'time_window'] == 'day').all()
    assert (out.loc[out['satellite'] == 'Terra', 'time_window'] == '8day').all()
    assert out['cell_id'].str.startswith('bc_dev_10km_').all()
    phase2_coverage.validate_coverage(out)


def test_15_run_coverage_import_stores(tmp_path: Path):
    _write_two_nc_pair(tmp_path)
    db_file = tmp_path / 't.duckdb'
    out = phase2_coverage_import.run_coverage_import(
        directory=tmp_path,
        region='bc_dev',
        cell_size_km=10,
        db_path=db_file,
        store=True,
    )
    loaded = phase2_database.load('observation_coverage', db_path=db_file)
    assert len(loaded) == len(out)


def test_16_run_coverage_import_no_duplicates(tmp_path: Path):
    _write_two_nc_pair(tmp_path)
    db_file = tmp_path / 't.duckdb'
    out1 = phase2_coverage_import.run_coverage_import(
        directory=tmp_path,
        region='bc_dev',
        cell_size_km=10,
        db_path=db_file,
        store=True,
    )
    phase2_coverage_import.run_coverage_import(
        directory=tmp_path,
        region='bc_dev',
        cell_size_km=10,
        db_path=db_file,
        store=True,
    )
    loaded = phase2_database.load('observation_coverage', db_path=db_file)
    assert len(loaded) == len(out1)