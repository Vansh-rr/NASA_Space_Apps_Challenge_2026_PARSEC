# PARSEC — Independent algorithm test and handoff

## Scope

The C11 scientific core is unchanged from the unified release: SHA-256 `c6349192685a304e5c6d4e04c28b11bdadac60f05274528e3fd67e4413570890`. Python geometry preparation is corrected for Shapely 2.x, atomic NASA input publication, early detection of existing output folders, automatic coverage-based holdout selection, and fallback to explicitly labeled cross-sensor tests where both training families cannot overlap. The new runner does not import any existing repository tests, Phase 1 or Phase 2 modules. Optional NASA acquisition files are unchanged from the earlier package and not required when extracted CSVs exist.

## Installation and execution

Create `PARSEC_Independent/` in the repository and put `parsec.c`, `prepare.py`, `test_parsec_independent.py`, `requirements.txt` there. Use Python 3.11/3.12 and GCC. Start inside that directory; the runner compiles its own executable in a fresh, uniquely named output directory.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python test_parsec_independent.py offline --install
python test_parsec_independent.py nasa --csv-dir ../PARSEC_Unified/output/nasa/extracted --max-folds 1
python test_parsec_independent.py nasa --csv-dir ../PARSEC_Unified/output/nasa/extracted --max-folds 4 --full
```

Every invocation prints `RUN DIRECTORY:` and writes `run_metadata.json`. There is no manual holdout prompt or output-path variable. The NASA runner selects holdouts by acquisition order, alternates target sensor families, ranks tiles only on availability/geographic coverage, and logs failed folds. `--max-folds 1` is a smoke test, not a statistically adequate experiment. Use the predeclared multi-fold run for reporting, including failures. `--full` also reconstructs fields using all observations; never score this reconstruction on the same detections as a holdout.

Optional acquisition from a directory of exactly 4 or 8 paired mask/geolocation science files, or live NASA Earthdata, requires `nasa/acquire.py`, `nasa/audit.py`, `nasa/extract.py`, `nasa/pilotlib.py`, empty `nasa/__init__.py`, and `requirements-nasa.txt`.

```bash
python test_parsec_independent.py nasa --raw-dir ../PARSEC_Unified/output/nasa/raw_l2 --install --max-folds 1
python test_parsec_independent.py nasa --live --install --start 2023-07-01 --end 2023-07-08 --per-sensor 2 --max-folds 4
```

The `--install` flag installs requirements into the currently active Python environment. No NASA credentials in command arguments or logs. Use extracted CSVs first to avoid any NASA network/authentication issues. For the physical reference comparison use `python test_parsec_independent.py reviewed --data-dir /path/to/reviewed/data` only after supplying all six documented files in `REAL_DATA_CONTRACT.md`.

## Freshly executed verification

Compiler: GCC with `-std=c11 -O3 -Wall -Wextra -Wpedantic -Werror`. Offline suite: 11/11 tests passed, zero failures/errors. The test suite includes an analytic one-cell posterior, full brute-force smoother comparison, polygon intersection weights, invalid input and provenance guards, no-leakage test, exact-versus-particle solver comparison, calibration/mixture variance, synthetic mask handoff, one-class metric handling, refusal of missing CSVs, and same-holdout comparator checks (including MODIS holdout and prevention of existing-output reuse). The offline runner also generated a new calibration and fitted an eight-bin/four-cell synthetic field, then ran a separate 20-cell stress experiment. A missing NASA directory was tested via the public command: exit 2 and ERROR.json, not a false pass.

### Synthetic calibration and harmonization

4,800 calibration posterior draws; all 11 diagnostics reported OK. Max split R-hat 1.01110347; minimum approximate ESS 564.565277; all 11 generating parameter values inside 95% credible intervals for this test seed.

| Metric | Constant baseline | PARSEC | Interpretation |
|---|---:|---:|---|
| FRP RMSE (MW) | 8.882919 | 5.146885 | Lower is better |
| FRP MAE (MW) | 8.593750 | 3.370537 | Lower is better |
| Signed FRP bias (MW) | 2.968750 | 2.111524 | Positive overestimate |
| Fire probability Brier | 0.377500 | 0.039389 | Lower is better |
| Fire probability log loss | 1.002934 | 0.177016 | Lower is better |
| 95% credible interval coverage | Not available | 100% | 32 simulated reference rows only |

RMSE reduction ~42.1%; Brier reduction ~89.6%, **versus constant synthetic baseline, not NASA**. Evaluation uses 32 synthetic truth rows (18 positive, 14 negative). Same synthetic benchmark as unified release, reproduced by actual fresh execution, not a new independent scientific experiment. Exact inference returned no warning. The large-grid stress experiment used 20 cells, eight bins, 6,000 particles after retry, minimum ESS fraction 0.00068733 and numerical warning true. This is a known limitation, not a scientific success.

Individual evidence files: `offline_tests.log`, `synthetic_validation_report.json`, `calibration_summary.csv`, `stress_report.json`.

## NASA comparison outputs

- `NASA_REPORT.json`: completed, skipped and failed folds; number of two-class and actual fusion folds; numerical warnings.
- `nasa_comparison_metrics.csv`: per-fold, per-stratum Brier, log loss, AUC (undefined when only one class), sample counts, observed and predicted rates, Brier skill vs constant and available alternatives.
- Each fold's `comparison_predictions.csv`: exact same held-out IDs/labels across all model variants. `all_available` uses all training sensors; it is a fusion model only when `actual_fusion=true`. `modis_only` and `viirs_only` use the same Bayesian solver with training restricted to the named sensor. Raw baselines average overlapping usable training detections, weighted by approximate polygon intersection area within the same nominal time bin. This is a simple detection-rate proxy, not the physical area burned or NASA's confidence probability. They can repeat area from multiple observations and only appear for supported subsets. No raw baseline is extrapolated into unobserved regions. The `same_bin_overlap_both` stratum compares all methods on identical rows having both raw baselines. Other strata must not be mixed. Raw binary probabilities are clipped to 1e-15 for numerical log-loss evaluation; Brier is the more straightforward comparison.
- `fold_*/all_available/field_posterior.csv`: posterior of the held-out reconstruction. `full_reconstruction/field_posterior.csv`, if requested, uses all observations and is not a holdout test.

Interpretation: lower Brier/log loss is better; positive Brier skill indicates reduction in squared probability error relative to the named baseline. The comparison is retrospective smoothing, not a forward forecast. One-class folds establish execution and one-sided predictive error only, not discrimination. No pooling of correlated folds or claims of statistical significance. Numerical-warning folds must not be treated as reliable evidence. If all folds have no eligible geometry, acquire different granules, preserve the report, and retry without selecting based on favorable labels. If only one family remains in training, label it cross-sensor prediction, not fusion. A zero count in the same-bin overlap stratum is a genuine absence of eligible comparison rows, not a software failure.

## Scientific blockers

No authentic NASA granules or extracted real CSVs were available in this execution environment. The NASA mask-to-inference pathway and comparative methods were tested with explicit synthetic pixel fixtures; live authentication, real HDF4 extraction, and real NASA predictive metrics were not rerun here. User-supplied CSV provenance is not automatically authenticated by filename checks. These reports cannot assert physical fire accuracy or superiority over NASA. The real mask pilot has approximate footprint polygons and nominal granule times, illustrative calibration and no FRP. Independent reference fire/no-fire and comparable FRP, reviewed physical footprints and scale consistency are required for `reviewed`. Real VIIRS FRP is still deliberately refused because retrieval support and dependence remain unresolved. The reviewed evaluator compares against the baseline supplied in the reference CSV on identical cell/time support; its validity depends on external scientific review. Phase 2 historical reconstruction, scalability and calendar validation remain separate engineering/scientific work.

NASA's MODIS Collection 6 publication reports a 1.2% daytime global commission error in its independent validation (Giglio et al., 2016, DOI 10.1016/j.rse.2016.02.054). This is not comparable to PARSEC's synthetic Brier score. NASA's VIIRS products and MODIS are primary satellite retrievals; PARSEC is downstream sensor fusion. See https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html.

## Git handoff

Do not commit `.venv/`, compiled executables, downloaded NASA data, `algorithm_test_output/`, or credentials. Stage only the four source/dependency files and the real-data contract, and optional acquisition files if required. Preserve your team's existing Phase 2 source and tests unchanged. The new runner can be used independently until both workstreams are ready to integrate.
