#!/usr/bin/env python3
"""Extract geolocated L2 fire-mask pixels from swath + matching geolocation granules.

Supports HDF5/NetCDF4 and optional HDF4 via pyhdf. Does not reinterpret FRP,
make cloud pixels negative, or calculate footprints. Granule times are nominal.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import math
import re
import sys
from pathlib import Path

import numpy as np

FIELDS = ['sensor', 'product', 'collection', 'granule_id', 'geolocation_granule_id',
          'time_utc', 'latitude', 'longitude', 'line', 'sample', 'mask_class',
          'usable', 'detected', 'source_file', 'geo_file', 'time_basis',
          'pixel_stride', 'product_format']
PRODUCTS = {'MODIS': {'MOD14', 'MYD14'}, 'VIIRS': {'VNP14IMG', 'VJ114IMG', 'VJ214IMG'}}
PATTERN = re.compile(r'\.A(?P<year>\d{4})(?P<doy>\d{3})\.(?P<hour>\d{2})(?P<minute>\d{2})\.')


def stamp(name):
    m = PATTERN.search(Path(name).name)
    if not m:
        raise ValueError(f'NASA granule acquisition date/time missing from filename: {name}')
    fields = {k: int(v) for k, v in m.groupdict().items()}
    if not 1 <= fields['doy'] <= (366 if fields['year'] % 4 == 0 and (fields['year'] % 100 != 0 or fields['year'] % 400 == 0) else 365):
        raise ValueError('invalid NASA day-of-year')
    t = dt.datetime(fields['year'], 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(
        days=fields['doy'] - 1, hours=fields['hour'], minutes=fields['minute'])
    if fields['hour'] >= 24 or fields['minute'] >= 60:
        raise ValueError('invalid acquisition clock time')
    return t


def _candidate(name, requested, keys):
    if requested:
        if requested in keys:
            return requested
        raise ValueError(f'dataset {requested!r} not found; available: {list(keys)[:40]}')
    wanted = {'fire mask', 'fire_mask', 'firemask'} if name == 'mask' else ({'latitude'} if name == 'lat' else {'longitude'})
    found = [k for k in keys if k.rsplit('/', 1)[-1].lower().replace('_', ' ').strip() in {v.replace('_', ' ') for v in wanted}]
    if len(found) != 1:
        raise ValueError(f'expected one 2D {name} dataset; found {found}; use --{name}-dataset explicitly')
    return found[0]


def read_array(path, field, requested=None):
    ext = Path(path).suffix.lower()
    if ext in {'.nc', '.nc4', '.h5', '.hdf5'}:
        import h5py
        with h5py.File(path) as f:
            keys = []
            f.visititems(lambda k, v: keys.append(k) if isinstance(v, h5py.Dataset) else None)
            k = _candidate(field, requested, keys)
            result = np.asarray(f[k][()])
        fmt = 'HDF5_NETCDF4'
    elif ext == '.hdf':
        try:
            from pyhdf.SD import SD, SDC
        except ImportError as e:
            raise ValueError('HDF4 requires pyhdf: python3 -m pip install pyhdf') from e
        h = SD(str(path), SDC.READ)
        try:
            keys = list(h.datasets().keys())
            k = _candidate(field, requested, keys)
            result = np.asarray(h.select(k).get())
        finally:
            h.end()
        fmt = 'HDF4'
    else:
        raise ValueError('unsupported granule format; expected .nc/.h5/.hdf')
    if result.ndim != 2:
        raise ValueError(f'{field} dataset must be 2D; found shape {result.shape}')
    return result, fmt


def mask_state(m):
    if m == 5:
        return '1', '0'
    if m in (7, 8, 9):
        return '1', '1'
    return '0', ''


def extract(args):
    sensor = args.sensor.upper()
    if args.product not in PRODUCTS[sensor]:
        raise ValueError(f'{args.product} is not an allowed {sensor} L2 product')
    if not args.collection.strip():
        raise ValueError('collection required')
    bbox = args.bbox
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
        raise ValueError('invalid bbox W S E N')
    if args.stride < 1:
        raise ValueError('stride must be >=1')
    if args.stride > 1 and not args.demo_subsample:
        raise ValueError('stride >1 is demonstration-only; use --demo-subsample and do not approve for calibration')
    mask_time = stamp(args.mask_file)
    geo_time = stamp(args.geo_file)
    if mask_time != geo_time:
        raise ValueError('mask and geolocation granules have different nominal acquisition times')
    firemask, a = read_array(args.mask_file, 'mask', args.mask_dataset)
    lat, b = read_array(args.geo_file, 'lat', args.lat_dataset)
    lon, c = read_array(args.geo_file, 'lon', args.lon_dataset)
    if firemask.shape != lat.shape or firemask.shape != lon.shape:
        raise ValueError(f'EXACT geolocation grid shape mismatch: mask={firemask.shape}, lat={lat.shape}, lon={lon.shape}')
    if args.sensor.upper() == 'MODIS' and a != 'HDF4':
        print('WARNING: MODIS source not HDF4; accepted for synthetic fixture testing only.', file=sys.stderr)
    if args.sensor.upper() == 'VIIRS' and a == 'HDF4':
        print('WARNING: HDF4 VIIRS product; verify product collection and mask class semantics.', file=sys.stderr)
    # Chunk rows into small batches; do not broadcast all coordinates at once.
    n, invalid, checked = 0, 0, 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS)
        wr.writeheader()
        for i in range(0, firemask.shape[0], args.stride):
            for j in range(0, firemask.shape[1], args.stride):
                checked += 1
                la, lo = float(lat[i, j]), float(lon[i, j])
                if not (math.isfinite(la) and math.isfinite(lo) and -90 <= la <= 90 and -180 <= lo <= 180):
                    invalid += 1
                    continue
                if not (bbox[0] <= lo <= bbox[2] and bbox[1] <= la <= bbox[3]):
                    continue
                raw = firemask[i, j]
                if not np.isfinite(raw) or raw != int(raw) or not 0 <= int(raw) <= 9:
                    invalid += 1
                    continue
                m = int(raw)
                usable, detected = mask_state(m)
                wr.writerow({
                    'sensor': sensor, 'product': args.product, 'collection': args.collection,
                    'granule_id': args.mask_file.name,
                    'geolocation_granule_id': args.geo_file.name,
                    'time_utc': mask_time.isoformat().replace('+00:00', 'Z'),
                    'latitude': f'{la:.9f}', 'longitude': f'{lo:.9f}',
                    'line': i, 'sample': j, 'mask_class': m,
                    'usable': usable, 'detected': detected,
                    'source_file': str(args.mask_file), 'geo_file': str(args.geo_file),
                    'time_basis': 'granule_nominal_not_pixel_time',
                    'pixel_stride': args.stride, 'product_format': a,
                })
                n += 1
    print(f'PASS: extracted {n} mask-classified pixel centers from {args.mask_file.name}')
    print(f'INFO: inspected {checked} coordinates, invalid/excluded {invalid}, stride {args.stride}')
    print('CAUTION: nominal granule time; no footprint overlap, FRP retrieval, or independent reference evidence verified')
    return n


def cli(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sensor', required=True, choices=['MODIS', 'VIIRS', 'modis', 'viirs'])
    p.add_argument('--product', required=True)
    p.add_argument('--collection', required=True)
    p.add_argument('--mask-file', required=True, type=Path)
    p.add_argument('--geo-file', required=True, type=Path)
    p.add_argument('--bbox', nargs=4, type=float, required=True, metavar=('W','S','E','N'))
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--mask-dataset')
    p.add_argument('--lat-dataset')
    p.add_argument('--lon-dataset')
    p.add_argument('--stride', type=int, default=1)
    p.add_argument('--demo-subsample', action='store_true')
    a = p.parse_args(argv)
    try:
        extract(a)
    except (OSError, ValueError, ImportError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(cli())

