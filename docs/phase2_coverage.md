# Observation coverage (Task 2.8)

Coverage tells the model whether a satellite could actually see a grid cell.
A missing fire detection is not always "no fire": the sky may have been
cloudy, or the satellite may not have been working.

## States

| State | Meaning |
|---|---|
| `observed` | The sensor had a clear view |
| `cloudy` | Cloud blocked the view |
| `unavailable` | No usable data (satellite not flying yet, or not processed) |
| `unknown` | We have no coverage information. Never treat this as "no fire" |

## Use it

```python
import pandas as pd
from phase2 import phase2_coverage, phase2_database

coverage = phase2_database.load('observation_coverage')
keys = pd.DataFrame(
    [('british_columbia_5km_45_1', 'S-NPP', '2023-07-26')],
    columns=['cell_id', 'satellite', 'window_start'],
)
print(phase2_coverage.get_coverage(keys, coverage=coverage, time_window='day'))
```

One row comes back per key, with `state`, `observed_fraction` and `source`.

## Get the data

The files are not in git. To recreate them:

1. Make a free NASA Earthdata account: https://urs.earthdata.nasa.gov
2. Open AppEEARS: https://appeears.earthdatacloud.nasa.gov
3. Extract, Area Sample, "Upload a request file", and choose
   `configs/appeears_bc_dev_firemask_2023_07.json`. Submit.
4. When the email arrives, download the three `.nc` files into
   `data/raw/coverage/`.
5. Run:

```
python -m phase2.phase2_coverage_import
```

Options: `--dir`, `--region`, `--cell-size-km`, `--demo`, `--no-store`.

If the upload is rejected, enter the request by hand: area longitude -123.05
to -120.02 and latitude 52.03 to 54.04, dates 2023-07-01 to 2023-07-31, layer
`FireMask` from `VNP14A1.002`, `MOD14A2.061` and `MYD14A2.061`, format
NetCDF-4, projection Geographic.

## What you should see (bc_dev box, July 2023, 5 km cells)

86,637 rows over 1,877 cells.

| Satellite | Window | Source | Notes |
|---|---|---|---|
| S-NPP | day | VNP14A1.002 | 31 days. Unavailable in every cell on 2023-07-26 |
| Terra | 8day | MOD14A2.061 | 5 windows |
| Aqua | 8day | MYD14A2.061 | 5 windows |

## Limits to know about

- **Only the small bc_dev box has coverage.** Rows use `british_columbia`
  cell IDs so they join with the rest of Phase 2. Cells outside the box
  come back as `unknown`.
- **MODIS coverage is 8-day, not daily.** AppEEARS does not offer the daily
  MODIS fire mask. An 8-day map reports cloud only if all 8 days were
  cloudy, so it is stored with `time_window = '8day'` and never answers a
  daily question. Daily MODIS would need another source, for example the
  Level 2 granules handled by the `nasa/` package.
- **VIIRS coverage comes from the 750 m bands** (gridded to 1 km), while
  the FIRMS VIIRS detections are 375 m. A good proxy for cloud, not an
  exact match.
- **Daily maps, not per overpass.** They say whether the satellite had a
  clear view that day, not at a given minute.
- Cells with fewer than 10 valid pixels are skipped.
- `dataset_versions` in the YAML has no `coverage` entry yet. The version
  is built in the module as `2.8.0+cfg<config_version>`.

## Mask classes

| FireMask class | State |
|---|---|
| 0, 1, 2 (not processed) | `unavailable` |
| 3 (water), 5 (land), 7 to 9 (fire) | `observed` |
| 4 (cloud) | `cloudy` |
| 6 (unclassified) | `unknown` |