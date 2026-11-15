# PARSEC repository organization

Source: uploaded `Nasa_Apps_2026-code (1).zip`, commit identifier
`33ada688256587455a99ae6329d4e5acdf8acb63` in its ZIP comment.

## Layout and responsibilities

```
Nasa_Apps_2026/
├── phase1_*.py                    # all nine files unchanged
├── phase2_run.py                  # one engineering + optional algorithm entry point
├── phase2_test.py                 # one independent verification entry point
├── phase2/
│   ├── phase2_config.py            # settings
│   ├── phase2_schema.py            # IDs and table contracts
│   ├── phase2_database.py          # DuckDB storage/query integration
│   ├── phase2_queries.py
│   ├── phase2_overlap.py           # common overlap observations
│   ├── phase2_grid.py              # existing geospatial grid
│   ├── phase2_temporal.py
│   ├── phase2_spatial_matching.py
│   ├── phase2_matching.py
│   ├── phase2_fire_events.py
│   ├── phase2_source_flags.py
│   ├── phase2_sensor_comparison.py # raw sensor comparison
│   ├── phase2_features.py
│   ├── phase2_splits.py
│   ├── phase2_dataset_builder.py
│   ├── phase2_model_interface.py   # existing match-group baseline/model interface
│   ├── phase2_prediction_schema.py
│   ├── phase2_metrics.py
│   ├── phase2_validation.py
│   ├── phase2_run.py               # original pipeline, extended by existing steps
│   ├── demo.py                     # synthetic fixture from original tests
│   ├── workflow.py                 # command orchestration, no numerical model logic
│   └── algorithm/
│       ├── parsec.c                # ONE canonical original C core
│       ├── prepare.py              # original Python scientific preparation
│       ├── test_parsec_independent.py
│       ├── requirements*.txt
│       ├── SHA256SUMS
│       ├── REAL_DATA_CONTRACT.md
│       └── nasa/                   # original Earthdata acquisition and extraction
├── tests_phase2/                   # original team tests + small new workflow tests
├── configs/                        # unchanged YAML
├── data/sample/                    # unchanged tracked sample files
├── docs/                           # contracts, reports, historical evidence
├── .github/workflows/phase2-tests.yml
└── tools/apply_organization.py      # guarded branch migration
```

The empty frontend/assets/notebooks/src/tests placeholder files from the branch
are preserved under `docs/original_placeholders/`; create actual `frontend/`,
`assets/`, and `notebooks/` directories when those implementations arrive. The
empty license and citation files are retained; no license or citation is invented.

## Why the two scientific paths remain separate

Phase 1 FIRMS hotspot observations → team Phase 2 grid, matching, features, events,
splits, match-group identity validation.

NASA Level-2 masks/geometry (or independently reviewed physical inputs) → unchanged
C model → posterior field, prediction metrics and numerical diagnostics.

The team grid is region-centred LAEA, whereas the exploratory algorithm builds a
separate EPSG:6933 grid with footprint intersection weights. Neither `cell_id` nor
FRP support can be treated as interchangeable. The engineering match-group interface
is a positive-detection regression contract, not a latent fire-field contract. No
fake bridge, parameter calibration or negative observations have been introduced.
Future frontend/Phase 3 code should consume the scientific `field_posterior.csv`
with the corresponding `bundle.json` geometry and `report.json` provenance, not
identity predictions presented as the C algorithm. A final scientific bridge into
calendar/database outputs remains to be implemented against that contract.

## One-command testing and running

From repository root in a Python 3.11 or 3.12 venv (C compiler GCC required):

```bash
python phase2_test.py --install
python phase2_run.py --demo --no-plots
```

The first executes the existing team suite, then the unchanged algorithm tests in a
separate process. The second runs an isolated synthetic demo through the complete
engineering workflow, then the unchanged C offline workflow. All test/workflow
runs use unique output folders; a failed requested subprocess gives nonzero exit.

Real engineering pipeline, after Phase 1 populated the desired database:

```bash
python phase2_run.py --start 2023-07-01 --end 2023-07-31
```

The step order is flags → overlap → grid → matching → events → comparison → features
→ splits → datasets → baseline → validation. Existing `--from` and `--only` are
available. The baseline remains `identity`. Explicitly add a NASA or reviewed data
source to run the C workflow, e.g. `--nasa-csv-dir /path/to/extracted`. Real database
runs retain the team's original version-keyed, insert-or-ignore behavior. Use a
fresh database/data directory or appropriate version bumps for changed region/date
scope; do not assume reruns on mixed scopes remove stale records.

Algorithm only (does not import the team database modules):

```bash
python phase2_test.py --algorithm-only
python phase2_test.py --algorithm-only --nasa-csv-dir /path/to/extracted --max-folds 4
python phase2_test.py --algorithm-only --nasa-live --install --max-folds 4
python phase2_test.py --algorithm-only --reviewed-data /path/to/reviewed_inputs
```

The latter requires all six reviewed inputs in the scientific data contract.
`--nasa-raw-dir` may replace `--nasa-csv-dir` if you have the original granules.
`--nasa-start`, `--nasa-end`, `--nasa-bbox` configure the Level-2 acquisition; these
are separate from engineering `--start`, `--end`, `--region`.

## Output paths

- `data/fires.duckdb`: existing Phase 1/2 real database, unchanged schema definitions.
- `data/phase2/`: team exports and reports; `grid/`, `comparison/`, `features/`,
  `model_input/`, `reports/validation/` and `runs/`.
- `data/demo/phase2_runs/<run>/workspace/`: isolated engineering demo database and exports.
- `data/test_runs/<run>/workflow_status.json`: exit status of requested test stages.
- `data/test_runs/<run>/algorithm/<run>/`: independent offline/NASA/reviewed reports.
- `data/phase2/runs/<run>/algorithm/<run>/`: algorithm reports when invoked with the real pipeline.
- `docs/algorithm_evidence/`: historical evidence shipped in the uploaded branch, not new real accuracy.

`PARSEC_DATA_DIR` can override `data/` for test and workflow isolation. Do not commit
NASA raw data, generated reports, DBs, compiled executables, venvs or credentials.

## Minimal changes and verification

- All nine Phase 1 Python files, both config YAML files, and sample CSVs unchanged.
- All ten original algorithm code/dependency files unchanged (C, seven Python scripts,
  two requirements files). The root `parsec.c` and `PARSEC_Independent/Parsec.c`
  were identical; consolidated under the lowercase canonical filename the runner expects.
- Existing 20 Phase 2 modules moved to one package, with imports adjusted. The raw
  comparison file had an original `rom __future__` syntax error, fixed to `from`.
- Existing team pipeline gains four stages that call the team's existing functions;
  missing test-split metrics are reported as missing rather than a KeyError.
- Direct VIIRS reference FRP aliases are excluded from match-group predictions.
  Existing identity model and C inference equations unchanged.
- All original test files retained, imports updated; pipeline/target-alias assertions
  expanded and two small new tests added. CI now invokes both offline suites.
- Source SHA256 checks run before C workflows. SHA256 of C:
  `c6349192685a304e5c6d4e04c28b11bdadac60f05274528e3fd67e4413570890`.
- Actual local verification: 11/11 independent algorithm tests, complete synthetic
  calibration and field validation, known larger-grid particle warning; 20 pure
  team/orchestration tests passed. All Python files compile. Full database tests and
  Parquet round-trip blocked locally by missing DuckDB/PyArrow; package installation
  failed due network/DNS restrictions. These tests are included, not claimed passed.
- No real NASA download, real physical validation or regional-scale stability claim
  was made by this reorganization. The algorithm's NASA comparison remains exploratory.

See `REORGANIZATION_TEST_REPORT.md` for the actual results.
