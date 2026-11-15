# Phase 2 setup and tests

## Install
```
python -m pip install -r requirements.txt
```

## Run Phase 2 on the BC July 2023 data
Needs the Phase 1 database first (`python phase1_run.py --real`).
```
python -m phase2.phase2_overlap --start 2023-07-01 --end 2023-07-31   # 2.2 overlap
python -m phase2.phase2_matching                                      # 2.4-2.6 matching
python -m phase2.phase2_fire_events                                   # 2.7 fire events
python -m phase2.phase2_database                                      # 2.15 row counts
```
Every step can be rerun safely: rows already stored are skipped.

## Settings
All in `configs/phase2.yaml` (regions, dates, matching limits, fire event limits).
Check them with `python -m phase2.phase2_config`. Change a value -> bump `config_version`.

## Tests
```
python -m pytest tests_phase2 -q
```
- Tests use small hand-made data in a temporary folder, never the real `data/` folder.
- No FIRMS key or internet needed.
- GitHub runs the same tests on every push to `code` or `main` (`.github/workflows/phase2-tests.yml`).
  Results: repo page -> **Actions** tab.

| File | Covers |
|---|---|
| `tests_phase2/test_phase2_grid.py` | 2.3 grid (Kai) |
| `tests_phase2/test_phase2_config_schema.py` | 2.1 config, schema, IDs |
| `tests_phase2/test_phase2_matching.py` | 2.2 overlap, 2.4 temporal, 2.5 spatial, 2.6 matching |
| `tests_phase2/test_phase2_events_database.py` | 2.7 fire events, 2.15 database + queries |
| `tests_phase2/conftest.py` | shared test data |

## New repository-level commands

```bash
python phase2_test.py --install              # original team suite + unchanged algorithm
python phase2_run.py --demo --no-plots       # isolated engineering + algorithm demo
python phase2_run.py --start 2023-07-01 --end 2023-07-31
python phase2_test.py --algorithm-only --nasa-csv-dir /path/to/extracted --max-folds 4
```
The original individual modules are available as `python -m phase2.phase2_<module>`.
The team pipeline includes grid, raw comparison, features and dataset exports as well
as its original seven steps. `--from` and `--only` remain available for partial runs.
See `REPOSITORY_ORGANIZATION.md` for migration and what has and has not been validated.

