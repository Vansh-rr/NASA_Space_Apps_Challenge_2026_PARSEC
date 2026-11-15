# Reorganization verification report

This report concerns the supplied code branch after reorganizing it, not the old
standalone ZIP or an independently validated satellite product.

| Check | Result |
|---|---|
| All nine Phase 1 `.py` files | Byte-for-byte identical |
| Both config YAML files and two sample CSVs | Byte-for-byte identical |
| Canonical C file | Byte-for-byte identical to both uploaded C copies and previous independent file |
| Original algorithm Python scripts and requirements | Byte-for-byte identical (10 source/dependency hashes total including C) |
| Python syntax | All source files compile |
| Independent C algorithm suite | 11/11 passed (fresh execution) |
| C strict GCC build | Passed as part of runner |
| Root `phase2_test.py --algorithm-only` | Exit 0; passed entire independent workflow |
| Team grid tests not requiring Parquet | 16 passed |
| New raw comparison and workflow tests | 4 passed |
| Original grid Parquet round trip | Blocked by missing PyArrow |
| Full team pytest suite | Collection blocked by missing DuckDB |
| Real NASA data / independent physical truth | Not run; external data/credentials required |

The dependency installation was attempted locally but failed due unavailable DNS/network.
The full team pipeline with its four new orchestration stages is **not yet certified**;
run `python phase2_test.py --install` and `python phase2_run.py --demo --no-plots`
in Codespaces. The test runner deliberately exits nonzero if the engineering suite fails.

## Fresh synthetic algorithm results

Same seed and inputs as the original independent tests; no C or scientific Python
changes. The results reproduce the previous benchmark.

| Metric | Constant synthetic baseline | PARSEC |
|---|---:|---:|
| FRP RMSE (MW) | 8.8829190022 | 5.1468853957 |
| FRP MAE (MW) | 8.5937500000 | 3.3705373680 |
| FRP bias (MW) | 2.9687500000 | 2.1115235184 |
| Brier | 0.3775000000 | 0.0393886343 |
| Log loss | 1.0029341294 | 0.1770163163 |
| Empirical 95% interval coverage | — | 1.0 |

32 reference cell-time records, 18 positives, 14 negatives, four synthetic groups.
These are not NASA accuracy scores. The 20-cell stress run retains its numerical
warning: execution is successful but the approximation is not stable.

Evidence files under `reorganization_evidence/` are from the fresh local runs.
Historical evidence from the uploaded code branch remains separate under
`algorithm_evidence/`. NASA comparisons are generated only after supplying actual
Level-2 observations. Reviewed physical accuracy still requires all six independent
reference/calibration files and scientifically reviewed footprint/FRP support.

## Migration checks

The migration script was executed against a separate copy of the uploaded branch:
42 obsolete paths removed and 82 paths copied; every resulting manifest hash
matched. Repeating the dry run planned zero changes. A separate trial with a
modified `phase2_matching.py` was rejected before writing any files. The counts
include documentation/evidence and relocated paths, not algorithm logic changes.
