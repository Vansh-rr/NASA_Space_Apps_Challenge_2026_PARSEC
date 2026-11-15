# Hosting preparation checks

Prepared from `ui-backend-connect` commit `eaf517f8758bfd3635e730dc7466fbfcc4bbd3ea` on 16 November 2026 (client date).

- Complete offline suite: 177 Python tests, 46 frontend tests, 11 independent C regression checks, and the TypeScript/Vite production build passed.
- Deployment-only regression checks: 9 passed, including project-scoped commands, no-execution dry runs, restricted/normalized CORS, rejection of absent/non-self-contained snapshots, and upload allowlists.
- Isolated API runtime: installed only `requirements-api.txt` with tested constraints in a fresh virtualenv. Copied only the Docker serving source set, config, published preview and a synthetic test database. All eight API views and allowed/blocked CORS checks passed. Shapely, PyProj, GeoPandas and NetCDF were absent from this environment.
- Cloudflare-style production build with an HTTPS API URL passed. An otherwise identical build with the API URL omitted failed as intended.
- The image build and Docker smoke checks are automated in `.github/workflows/cloud-run-container.yml`; Docker is not available in the local preparation environment. Consult that workflow for the actual image-build result.

No paid Google resources were created, no production database was uploaded and no Cloudflare deployment was performed during repository preparation. Actual hosting requires a project linked to billing, provider authentication and the genuine `data/fires.duckdb` snapshot. The existing solver stress warning and scientific validation limits are unchanged.
