# Repository audit and corrections

Date: 16 November 2026 (client date).

## Scope and source selection

All four uploaded ZIP inventories were compared by SHA-256 for every file. The two `ui-backend-connect` archives were byte-identical. That version contained all files from `bayesian-model-preview` and `main (2)`, plus the API/frontend integration and committed preview. It is the repair base. No remote branch or Git history was supplied or changed. The source is a snapshot, so later remote edits require manual reconciliation.

Reviewed areas: FIRMS ingestion/schema/cache handling, raw and derived database adapters, configuration, overlap/matching/events, features/splits/model plumbing/validation, historical coverage and analytics, protected C engine and NASA adapters, preview publication/readback, FastAPI routes, React data services/charts/map/provenance, dependency setup, CI and documentation. Existing tests were run before changes; regressions were added for confirmed faults. This is a source and automated-test review, not proof that every possible defect is absent.

## Confirmed findings and repairs

| Severity | Finding | Correction and verification |
| --- | --- | --- |
| High | Matching divided object arrays of timezone-aware Timestamp values by NumPy timedelta64. The initial run had 9 failures and 13 errors across matching, model, pipeline and API tests. | Convert both acquisition arrays to explicit UTC datetime64[ns] before computing minute differences. All affected suites now pass. |
| High | Satellite launch/availability was treated as proof of observation coverage. Missing history periods became real zero detections, potentially biasing seasonal baselines. | Default to `unknown` or `partial_observed`. Complete `observed`/`no_detections` periods require explicit satellite/day regional coverage evidence. Baselines exclude unknown/partial periods. Tests prove that verified zeros and unknowns remain distinct. |
| High | React calendar, daily counts and daily FRP filled absent rows or missing FRP with zero. Missing model runs appeared as zero-valued KPIs. | Preserve nulls and chart gaps, grey unknown calendar months, and null unavailable KPIs. Keep actual supplied zero counts. |
| High | Model run IDs used config labels but did not fingerprint input contents. Historical validation could silently compare old predictions against newly changed labels/features. | Include a stable digest of sorted model inputs in run identity and refuse validation when the current input differs or the stored run predates fingerprints. A database mutation regression checks refusal and a new run ID. |
| High | Changing settings without manually changing config_version could reuse old derived table versions. | Include a deterministic settings digest in derived versions, independent of demo output mode. Bump config release to 2.2.0. The API filters current matching/analytics versions. |
| High | The API selected the newest harmonized run globally, including synthetic or unrelated-region runs. | Select compatible region/current matching-version runs and require synthetic provenance to match API demo mode. Regression verifies synthetic predictions do not leak into real mode. |
| High | NaN or negative FRP predictions and incomplete intervals could be accepted. Metric arrays could broadcast silently; reversed intervals were not rejected. | Require complete finite, nonnegative model predictions and paired interval bounds. Validate metric dimensionality, shapes, FRP domain and interval order. |
| Medium | `skill = 1 - model / baseline` was applied to bias, correlation, R2 and interval coverage, and could divide by zero. | Define relative skill only for nonnegative error metrics with positive baseline error. Other skill values remain undefined. Guard the perfect-residual histogram from zero-width bins. |
| Medium | Pipeline restarts loaded a shared Parquet export, which could belong to another selected database or date range. | Resume by extracting from the explicit source database/region/dates. A regression poisons the shared export and verifies the chosen database still supplies the correct rows. |
| Medium | Derived `INSERT OR IGNORE` retained obsolete values on rerun; an empty result did not create its table. | Upsert supplied derived keys, reject duplicate primary keys within a batch, and create empty schemas. Raw observations remain append/idempotent. Tests check refreshed values and empty tables. |
| Medium | `tables=[]` created every derived table; an empty SQL IN filter generated invalid syntax; nullable filters used equality; migration identifiers were not allowlisted. | Distinguish None from an empty table list, make empty filters false, use IS NULL, and validate migration table names. |
| Medium | Explore stopped after 50,000 points. Model Preview stopped after 10,000 rows and silently used a hardcoded BC bbox. | Add observation offsets and consume every page with count/progress checks. Preview uses the metadata bbox and pages until total is loaded. Truncated/changing responses raise visible errors. |
| Medium | Invalid calendar dates could reach DuckDB or pandas as server errors; health reported success with a missing database. | Validate actual calendar values, reject reversed date ranges, and return controlled 503 readiness/schema failures. Empty-but-built tables remain valid empty results. |
| Medium | Demo comparison/activity data was labelled as real by frontend response objects. | Propagate demo provenance from API through Analytics, Compare, Explore badges and calendar labels. |
| Medium | The map drew assumed scan/track rectangles enlarged sixfold, which could look like measured fire extents. | Use point markers for detection centres. No inferred pixel or burned-area geometry is displayed. |
| Medium | Preview file hashes were checked, but semantic values could still be inconsistent. | Check provenance consistency, warning/physical-validation flags, unique complete cell-time keys, cell membership, probability and coordinate bounds before serving. |
| Medium | About described an implemented MAP/log-FRP harmonizer and validated common scale that the connected default identity baseline does not provide. Frontend setup documentation still claimed there was no backend. | Describe the actual identity baseline and separate discrete-field Bayesian preview, its illustrative calibration, real API connections and scientific limits. Correct demo database startup paths. |
| Medium | Original CI and the existing test command covered Phase 2 only, omitting API, preview and frontend. | Add `run_tests.py`, prerequisite checks, optional dependency installation, isolated output, timeout/nonzero handling, JSON/JUnit/log reporting and CI covering all branches/PRs. Include tested Python constraints and retain the npm lockfile. |
| Low | Nested historical ZIPs and an editor history file complicated repository copies and push reviews. | Exclude/remove only the known obsolete nested archives/history file. Ignore generated builds, dependencies, local environments, credentials and test outputs. Historical audit logs remain identified as old evidence. |

## Scientific limits that cannot be repaired by code alone

The committed preview is a NASA-mask exploratory reconstruction, not an independent physical FRP validation. Its selected holdout has 11 labels: zero fire, eleven nonfire. All listed attempted folds are one-class. The selected all-available Brier score is about 0.004295, while the constant-training baseline is 0.0025; a smaller Brier score on this fold favors that constant baseline. These values measure agreement with held-out mask labels only and cannot establish accuracy for actual fires, physical FRP, general regional performance or superiority over NASA. AUC/positive-class recall are not identifiable on an all-negative fold. The raw NASA granules were not independently authenticated or downloaded during this repair.

The independent C engine, its input adapters and source-checksum contract were left byte-for-byte unchanged. The analytic/brute-force, particle-comparison, holdout leakage, calibration and variance tests passed. Its stress test still reports a numerical warning. More particles, a different solver regime or a validated algorithm revision may be needed for larger fields. This warning is retained in reports, not relabelled as a pass for numerical stability.

## Remaining implementation limits

- `store()` refreshes keys present in the supplied batch, not rows absent from a smaller later window. Existing derived state can therefore contain earlier keys. Use a fresh derived experiment or back up and explicitly rebuild the relevant version when input support shrinks.
- The engineering reference is a sum of matched VIIRS reported FRP. It is not independent ground truth, and 375 m detections can share a coarser FRP retrieval. The protected real-data adapter continues to refuse unsupported physical VIIRS-FRP inference.
- The optional regional verified-coverage attestation is not inferred from an imported partial mask or a satellite launch date. It needs independent QA and documented spatial/time support. No such attestation was fabricated.
- CLI options that change date support are not a substitute for storing a complete experiment snapshot. Input fingerprints detect changed validation inputs but do not archive/recover old training features automatically.
- External basemaps need network access. Place-name search remains a fixed demo catalogue; coordinates are supported. Authentication, live alerts, a production forecast, download UI and production deployment were not added.
- Browser interaction and visual end-to-end automation were not run. Frontend service tests, TypeScript checking and production build passed; API smoke tests exercised the documented local demo.
- Existing pandas/Shapely/Starlette deprecation warnings remain. The protected algorithm adapters were not rewritten solely to eliminate warnings. Tested dependency constraints record the verified environment, not a blanket claim about all platforms or future package versions.

## Applying and pushing

Use `START_HERE.md`. The outer bundle also contains `apply_fixes.py`, a hash-guarded dry-run installer, and `PARSEC_fixes.patch` against the UI/backend upload. The installer accepts known originals from all four uploaded snapshots and refuses unknown local modifications. It does not contact GitHub, force-push or merge a branch.
