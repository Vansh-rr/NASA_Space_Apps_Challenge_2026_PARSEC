# PARSEC repository repair

The corrected repository is in `PARSEC/`. The UI/backend uploads were byte-identical and included every file from the other two source versions. The most complete UI/backend version was used as the base. Existing About content and the Bayesian preview are retained with corrected descriptions.

## Test everything with one command

From `PARSEC/` after installing prerequisites:

```bash
python run_tests.py --install
```

This installs the tested Python constraints and frozen npm lockfile, runs Phase 1 ingestion tests, Phase 2 pipeline tests, Phase 3 API tests, preview exporter tests, runner tests, independent C tests and synthetic calibration/stress checks, frontend tests and the TypeScript/production build. Subsequent runs need no downloads:

```bash
python run_tests.py
```

Requirements: Python 3.11+ (verified on 3.12), Node.js 24 LTS with npm, and GCC on PATH. On Windows, use WSL2 or GitHub Codespaces for the C suite. A fresh Ubuntu Codespace already provides GCC. These tests need no FIRMS key or Earthdata login. `--install` needs internet access.

Results go to `test-results/<run>/summary.json`, with stage logs and pytest JUnit XML. Failure returns a nonzero exit status. Explicit `--skip-frontend` or `--skip-algorithm` options are marked as a partial suite. The preview tests still need GCC even when the separate algorithm stage is skipped.

A successful C test run can include a reported particle stress warning. Read `stress_status.json` inside the algorithm output. That warning remains visible and is not a numerical stability pass. Passing software tests does not establish real NASA accuracy.

## Apply to your existing repository

Keep this package outside your clone. Start with a clean clone or commit/stash your own work. Replace `YOUR_REPOSITORY_URL` below with the real repository URL.

```bash
git clone YOUR_REPOSITORY_URL parsec-work
cd parsec-work
git switch -c fix/repository-audit
python ../PARSEC_Repair_Package/apply_fixes.py .
python ../PARSEC_Repair_Package/apply_fixes.py . --apply
python run_tests.py --install
git status --short
git diff --stat
git add -A
git diff --cached --stat
git commit -m "Fix PARSEC pipeline, data semantics and repository checks"
git push -u origin fix/repository-audit
```

Then open a pull request for that branch on GitHub. There is no force push, branch deletion or automatic merge. The installer is a dry run by default. It accepts original file hashes from any of the four uploads, checks the corrected payload hashes, and stops before any write if it encounters an unknown local version. It does not send messages or push anything itself. Existing secrets, databases and unrelated files are not part of its copy plan.

If your clone has changed since the uploaded snapshots, use `git diff` to reconcile the listed conflicts manually. `PARSEC_fixes.patch` provides a conventional diff relative to the UI/backend base. Use `git apply --check ../PARSEC_Repair_Package/PARSEC_fixes.patch` before applying that alternative. Do not apply both methods.

## Run the app locally

After testing, build a separate demo database for a local demonstration:

```bash
python -m phase2.demo
python -m phase2.phase2_run --demo --no-plots
```

These module commands build `data/demo_fires.duckdb`, which the API selects with `PARSEC_DEMO=1`. The isolated `phase2_run.py --demo` wrapper instead writes a new per-run workspace and is intended for experiments.

Start the API in one terminal:

```bash
PARSEC_DEMO=1 python -m uvicorn phase3.api:app --host 127.0.0.1 --port 8000
```

Start the UI in another:

```bash
cd firesync-app
npm run dev
```

The default frontend API URL is `http://localhost:8000`. `firesync-app/.env.example` documents the override. A relative API base such as `/api` also works with a correctly configured reverse proxy. Demo data is labelled as demo in API comparison metadata. The separately committed Bayesian mask preview is exploratory; it is not the demo identity baseline.

## Existing databases and scientific limits

The config release is now 2.2.0. Derived versions also include a digest of the settings. Back up any existing real database, then rerun the Phase 2 pipeline with the intended date range and config. Raw observations are retained. Older derived versions remain stored but are filtered out by the updated API. Runs without an input fingerprint must be rebuilt before validation.

Derived upserts refresh values for keys supplied in a rerun; they do not remove old keys that disappear from a narrower input window. For a clean, comparable evaluation, use a fresh derived database from your verified raw input, a separate `PARSEC_DATA_DIR`, or explicitly back up and remove the relevant derived version before rebuilding. Do not mix experiments by shrinking the date range in a populated version and assuming all older rows were deleted.

The FIRMS hotspot lists do not establish complete coverage. Historical periods with detections but no attested full-region coverage are `partial_observed`; empty ones are `unknown`. Both stay out of seasonal baselines. The optional `verified_coverage` argument of `make_history` / `build_history` accepts `satellite,date,support_evidence` only when complete usable regional coverage was independently established. It is never inferred automatically from hotspot presence, launch dates or a few gridded mask pixels.

The provided preview contains 11 holdout labels in its selected fold, all nonfire. AUC and recall for actual fires cannot be estimated from that fold. Physical FRP is unvalidated. No new live NASA acquisitions or independent field validation were performed in this repair.

See `PARSEC/docs/REPOSITORY_AUDIT.md` and `PARSEC/docs/REPAIR_TEST_RESULTS.md` for findings and measured results.
