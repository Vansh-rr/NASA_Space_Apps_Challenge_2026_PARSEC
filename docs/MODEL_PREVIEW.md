> This original integration note is retained as historical context. The current repository includes the actual API, frontend and a committed exploratory payload. Use `START_HERE.md`, `docs/website_setup.md` and `docs/REPOSITORY_AUDIT.md` for the tested current setup. Historical statements below that no UI/backend was supplied apply to the earlier handoff only.

# PARSEC Bayesian model preview — integration handoff

## Scope

This is an additive integration patch for the repaired repository, not a new algorithm. No protected source files, engineering code, dependencies or existing routes are changed. The actual UI/backend branch was not supplied; its routing framework and deployment paths are not assumed. Keep the existing identity baseline and its disclaimer. The new read-only grid preview is a separate product.

## Install and test

From a clean checkout containing `phase2/algorithm/SHA256SUMS` and `phase2/workflow.py`, copy `phase2/model_preview.py`, `test_model_preview.py` and this document into their indicated paths. The ZIP has repository-relative paths. Check the existing source hashes:

```sh
(cd phase2/algorithm && sha256sum -c SHA256SUMS)
python -m pip install -r phase2/algorithm/requirements.txt
python -m unittest test_model_preview -v
```

The seven tests use simulated masks in temporary directories and the genuine C executable. They are not real NASA scientific evidence. No test fixtures or synthetic generated posterior outputs are included in the patch.

## Generate the real preview (choose one input)

Prefer reusing the completed NASA run with `--full` if available:

```sh
find data phase2/algorithm -name NASA_REPORT.json -print 2>/dev/null
python -m phase2.model_preview --run /absolute/path/to/run_directory
```

The run directory is the parent of `NASA_REPORT.json`, not a fold directory. It must contain `run_metadata.json`, `fold_plan.json`, `fold_XX/input/bundle.json`, `field_all.txt`, `field.txt`, a full reconstruction and the separate comparison reports. Use an unchanged runner/core. If only CSV masks are available, use their actual directory:

```sh
python -m phase2.model_preview --csv-dir /absolute/path/to/extracted --max-folds 4
```

The input must be the extracted Level-2 mask/geolocation pixel CSVs, NOT the FIRMS hotspot database or sample data. To download fresh observations:

```sh
python -m phase2.model_preview --live --install --start 2023-07-01 --end 2023-07-08 --max-folds 4
```

This uses the existing Earthdata acquisition code and may prompt for credentials. The small pilot only considers up to two granules per sensor by default. The default bbox is the previously used BC study rectangle `-139 48 -114 60` (not a political boundary). If overlap is inadequate, acquire different granules or a different period, inspect the run report and rerun. No synthetic fallback. A pilot is a tiny selected tile, not a province-wide/month-wide result. The exporter will refuse publication if no completed, warning-free fold with both sensors in its full reconstruction is available. A one-class holdout or cross-sensor-only training fold is explicitly reported, not evidence of fusion advantage. The first eligible fold in acquisition order is selected without ranking scores. It preserves all selected full-fit rows, checks support and input consistency, joins grid geometry and writes a compact package atomically. The real acquisition and actual backend were not tested here. The runner checks lineage format, not authenticity of supplied CSVs; verify these are real NASA files before committing. Do not use test fixtures as publication data.

## Output layout

`model_preview/bc-july-2023/` by default; override via `--out`. Choose a new output path for a repeat (existing outputs are never overwritten). The name describes a study pilot, not its temporal or spatial extent; show actual coverage from metadata. Raw acquisitions and test runs are kept under gitignored `data/model_preview_runs/`.

- `metadata.json`: model run ID, actual bounds, first/last bins, counts, intensity levels, source hashes, granule IDs, disclaimer.
- `field.json`: API-ready `{items,total}` with unchanged C values, centroid coordinates, coverage and provenance.
- `cells.geojson`: cell polygons keyed by `cell_id`; GeoJSON coordinates longitude, latitude.
- `field_posterior.csv`: exact original C output for cross-checking.
- `report.json`: exact C numerical diagnostics, full-observation reconstruction.
- `validation.json`: separate held-out prediction evaluation, warnings, fold coverage and failure reasons.
- `comparison_metrics.csv`: matched held-out detection scores (not physical FRP accuracy).
- `manifest.json`: checksums of the seven files.

The three source patch files are small. The preview is precomputed once; no C execution in an HTTP request. Verify the real exported package before sharing:

```sh
python - <<'PY'
from phase2.model_preview import PreviewStore
s=PreviewStore('model_preview/bc-july-2023')
print(s.metadata)
print(s.field('2023-07-01','2023-07-31',[-139,48,-114,60],limit=2))
print(s.validation['comparison']['actual_fusion'])
PY
```

## Backend adapter (framework independent)

Instantiate once at application startup (or lazily once) using the explicit deployed artifact path, and return 503 if it is unavailable. `PreviewStore` checks all manifest hashes. It requires only standard library at read time. Use paths relative to the repository, not a working-directory assumption. Map validation errors to HTTP 400/422. Do not change the existing match-group endpoint or register a fake FRP predictor.

```python
from phase2.model_preview import PreviewStore
store = PreviewStore(REPO_ROOT / 'model_preview' / 'bc-july-2023')
# GET /api/v1/model-preview/metadata -> store.metadata
# GET /api/v1/model-preview/cells    -> store.geometry
# GET /api/v1/model-preview/field    -> store.field(start, end, bbox, limit, offset)
# GET /api/v1/model-preview/calendar -> store.calendar(start, end, bbox)
# GET /api/v1/model-preview/validation -> store.validation
```

`start`/`end` are inclusive UTC YYYY-MM-DD, bbox is west,south,east,north (list or comma-separated string); field limit/offset are integer, limit 1..10000; sorted time/cell ID. Calendar uses the same centroid filter and dense UTC days with null activity for missing days. `observed` means a modeled cell has direct usable observations, not that a fire was verified; `model_only` means an estimate without direct observation. No-data days are null, not zero. These routes are proposed; they are not registered in an actual web server by this patch. The existing `api_test.py` full profile can compare `/field` against the original CSV once the backend exposes the matching contract (or the team adapts its test route mapping to the separate preview endpoints).

## Frontend implementation

Add a Model Preview tab or section. Use `/metadata` to show the actual limited extent and dates, `/cells` for polygons, `/field` for time slider and p_fire heatmap, `/calendar` for daily expected active cell-time bins, `/validation` for separately measured Brier/log loss and comparison strata. Join using `cell_id`. Display probability as model-estimated, do not count distinct fires or burned area. Distinguish model-only from directly supported estimates. Keep the FRP proxy out of the existing matched-detection FRP chart; if displayed at all label it as **illustrative model FRP proxy (MW)**, with credible intervals and `physical_frp_validated=false`. Do not use it for scientific physical FRP claims. Holdout comparisons only score detection prediction on matched strata; do not compare raw metrics across different samples or claim NASA superiority. Leave the identity disclaimer intact. Explore can connect separately to existing raw data API; use the preview overlay only on its actual covered cells/time.

## Commit plan

Use an isolated feature branch based on `ui-backend-connect` once it contains the repaired algorithm. If it does not contain the repaired branch, coordinate a merge of `repository-repair` first; do not overwrite collaborators' code. Commit only the new three source files, and then optionally commit the small genuine verified preview directory in a second commit (or use a shared release artifact if too large). Check data sharing policy. Do not commit raw NASA granules, credentials, generated run folders, virtual environments or binaries. Keep `.gitignore` unchanged. Open a PR into the team's integration branch, then merge to main after UI and API smoke tests.

## Verification in the supplied repaired repository

- Original ten SHA-256 guards passed (C checksum `c6349192685a304e5c6d4e04c28b11bdadac60f05274528e3fd67e4413570890`).
- Seven integration tests passed with temporary simulated mask observations: actual C execution; exact CSV/JSON posterior agreement; pagination/geometry; null days and aggregation; separate holdout/full inference; tamper detection; warnings, mismatch and invalid-range rejection.
- No authentic Level-2 data or real Bayesian output was available in the supplied archives. Real predictive scores and physical accuracy have not been measured here. No real data were fabricated or bundled.
- No UI or HTTP routes in the repaired snapshot; actual `ui-backend-connect` was not available for inspection. The backend adapter is ready for registration but not a completed deployed integration.
