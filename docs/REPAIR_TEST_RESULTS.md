# Repair verification

Verified 16 November 2026 (client date). Environment: Linux, Python 3.12.14, Node.js 24.22.1, npm 11.9.0, GCC 14.2.0. Python constraints are recorded in `requirements-tested.txt`; npm uses the unchanged committed lockfile.

## Results

| Check | Result |
| --- | --- |
| Initial Python suite before repairs | 123 passed, 9 failed, 13 setup errors (145 total) |
| Final Python suite | 168 passed |
| Final frontend suite | 43 passed in 6 test files |
| Independent C offline regressions | 11 passed |
| Synthetic calibration-to-validation workflow | Passed |
| TypeScript check and Vite production build | Passed |
| One-command dependency installation | Passed for Python and npm |
| Documented demo engineering pipeline | Passed |
| Local API smoke checks | 8 endpoints returned HTTP 200 |
| Particle stress execution | Completed; numerical warning remains true |

The 222 test executions are software checks, not a count of independent real-data validation samples. The preview exporter tests use simulated masks with the genuine C executable. The app smoke test uses the synthetic demo database and the existing exploratory preview.

The final release suite ran `python run_tests.py`. The preceding `python run_tests.py --install` also completed successfully, confirming the documented installation path. Both summaries and final per-stage logs are included in `docs/repair_evidence/`.

The final ordinary runner stages took approximately 33.3 s for Python, 7.0 s for the independent C stage, 0.7 s for frontend tests and 1.5 s for the build on this environment. First installation took longer and depends on the network. These timings are not performance guarantees.

Remaining warnings are pandas concatenation compatibility, the Shapely transformation deprecation, and a Starlette/httpx integration deprecation; the installed versions still completed the suite. The particle stress warning is a separate, substantive solver diagnostic. See `repair_evidence/stress_status.json`; it is not suppressed or counted as a stability pass.

The exact reproduction command is:

```bash
python run_tests.py --install
```

This records logs, pytest JUnit XML and JSON under an isolated `test-results/<run>/` and exits nonzero on any requested-stage failure. Test prerequisites are explicit; missing Node/GCC/dependencies are not silently marked as passed. No live NASA acquisitions, independent physical FRP validation, production deployment or interactive browser testing were performed.
