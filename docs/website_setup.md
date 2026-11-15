For public Google Cloud Run + Cloudflare Pages hosting, use [CLOUD_RUN_CLOUDFLARE.md](CLOUD_RUN_CLOUDFLARE.md). The instructions below are for local development.

# Website setup

Run from the repository root. Use Python 3.12, GCC and Node.js 24 LTS.

```bash
python -m venv .venv
source .venv/bin/activate
python run_tests.py --install
```

For a deterministic local demo, build the API's normal demo database:

```bash
python -m phase2.demo
python -m phase2.phase2_run --demo --no-plots
PARSEC_DEMO=1 python -m uvicorn phase3.api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd firesync-app
npm run dev
```

Open the URL printed by Vite. The API docs are at `http://localhost:8000/docs`. For a real database, omit `PARSEC_DEMO=1` and populate `data/fires.duckdb` from verified inputs first. Optional `PARSEC_DB_PATH` selects an explicit database. `PARSEC_DATA_DIR` changes the default data directory and must be consistent across source-building/API processes.

The `phase2_run.py --demo` wrapper isolates every experiment under `data/demo/phase2_runs/<run>/workspace`. It does not fill the API's default `data/demo_fires.duckdb`. To serve that wrapper output, set `PARSEC_DB_PATH` to the exact generated demo database and also set `PARSEC_DEMO=1`.

`PARSEC_CORS_ORIGINS` controls allowed UI origins (comma-separated, current default `*`, read-only API). Restrict it to the intended origins when deploying. This prototype has no user authentication. `VITE_API_BASE_URL` configures the frontend API URL; use `.env.local`, not committed secrets. A relative `/api` requires a reverse proxy that strips or routes the prefix consistently. For a production static host, provide SPA fallback to `index.html` for client-side routes.

Explore, Compare and Analytics are connected to the API. The backend returns loaded hotspot observations; no rows do not prove zero fires. Model Preview is a separate committed read-only exploratory payload with checked file hashes. It does not run inference inside API requests.

Troubleshooting:

- Health 503 means the selected database is missing, unreadable or lacks observations. Check the actual database path and seed/build commands.
- History 503 means the history/analytics tables have not been built. Empty but built tables return empty results.
- Missing matching-version results after an upgrade mean Phase 2 must be rebuilt using the new settings digest. Back up existing data first.
- A blank basemap can mean external tile access failed. The map displays a tile error separately from a data error.
- Missing GCC or Node dependencies are reported by `run_tests.py`; the runner does not silently skip them.

The place-name search remains a fixed demo catalogue. Enter coordinates for locations outside that catalogue. The prototype does not offer live fire alerts, a production forecast, a verified burned-area product, or an implemented download screen.
