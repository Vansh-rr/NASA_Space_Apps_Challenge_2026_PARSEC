# Phase 2 Data Contract

Rules every Phase 2 module follows so the pieces fit together, whichever harmonization method is chosen.

## 1. Settings
- All settings live in **`configs/phase2.yaml`**. Nothing is hard-coded in the modules.
- `phase2_config.py` only **reads and checks** that file: `from phase2.phase2_config import get_config`.
- Change a value → bump `config_version`. Every derived table stores the version it was made with.
- Check the file: `python -m phase2.phase2_config`

## 2. Data sources
- Phase 2 reads Phase 1's `observations` table (DuckDB) and **never changes it**.
- Phase 2 tables point to Phase 1 rows by `observation_id`.
- Demo/synthetic output goes to `data/demo/phase2/` (`demo_mode: true`), real output to `data/phase2/`. They never mix.

## 3. IDs (`phase2_schema.py`)
Same inputs always give the same ID, so reruns don't create duplicates.

| ID | Made by | Example |
|---|---|---|
| `observation_id` | Phase 1 | sha256 hex |
| `cell_id` | `grid_cell_id(size, ix, iy)` | `g5km_-12_40` |
| `overpass_id` | `overpass_id(satellite, daynight, first_utc)` | `ovp_…` |
| `match_group_id` | `match_group_id(modis_observation_id, config_version)` | `mg_…` |
| `event_id` | `event_id(first_observation_id, method, config_version)` | `ev_…` |
| `model_run_id` | `model_run_id(name, version, dataset_version, params)` | `run_…` |

## 4. Tables
Defined in `phase2_schema.TABLES` (columns + primary key). `create_table_sql(name)` gives the SQL.

| Table | Task | One row = |
|---|---|---|
| `overlap_observations` | 2.2 | one detection inside the overlap period and region |
| `overpass_groups` | 2.4–2.6 | one satellite pass over the region |
| `match_candidates` | 2.4–2.6 | one MODIS–VIIRS pair close enough in time and space |
| `matched_observations` | 2.4–2.6 | one VIIRS detection in a MODIS match group (one-to-many) |
| `unmatched_observations` | 2.4–2.6 | one detection with no partner, with a reason |
| `dataset_splits` | 2.12 | one unit's split (`train` / `validation` / `test`) |
| `model_runs` | 2.13 | one model run |
| `model_predictions` | 2.13 | one prediction |
| `model_validation_results` | 2.14 | one metric for one group |
| `grid_cells`, `grid_observations` | 2.3 | draft, owner may change |
| `fire_events`, `fire_event_observations` | 2.7 | draft, owner may change |
| `observation_coverage` | 2.8 | draft, owner may change |
| `source_history_flags` | 2.9 | draft, owner may change |
| `matched_features` | 2.10 | draft, owner may change |

## 5. Matching = groups, not pairs
One MODIS pixel (~1 km) usually covers several VIIRS pixels (~375 m). So a **match group** is one MODIS detection plus all VIIRS detections matched to it. Matching only **pairs** detections; it never corrects values.

## 6. Model input and output (2.13)
A model gets one row per **unit** (`match_group`, `grid_cell` or `event`):

| Column | Meaning |
|---|---|
| `unit_id`, `unit_type` | what the row is |
| `split` | `train` / `validation` / `test` (from `dataset_splits`) |
| `source_value` | value being converted, e.g. MODIS FRP |
| `reference_value` | other sensor's value, e.g. summed VIIRS FRP; used only for fitting and evaluation |
| any other numeric columns | features (from 2.10) |

It returns `model_predictions`: `predicted_value`, optional `predicted_lower` / `predicted_upper`. A **no-correction baseline** (`predicted_value = source_value`) is always available for comparison.

## 7. Splits (2.12 → 2.13/2.14)
`dataset_splits` must keep a whole fire event or match group in **one** split. A random split by single detection leaks information and makes results look better than they are.

## 8. Units
Time UTC · coordinates degrees (WGS84) · distance km · area km² · FRP MW · temperature K · time differences minutes.
