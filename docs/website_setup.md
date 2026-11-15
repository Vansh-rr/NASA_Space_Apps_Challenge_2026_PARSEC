# Website setup: run the API and the FireSync UI locally

This guide starts the PARSEC website on your own machine: the API (`phase3/api.py`, FastAPI) reads
`data/fires.duckdb`, and the UI (`firesync-app/`, Vite + React + TypeScript) shows it in the browser.

Commands are for Windows PowerShell, run from the repo root unless a step says otherwise.
On macOS or Linux, use `source .venv/bin/activate` instead of `.\.venv\Scripts\Activate.ps1`.

## What is real and what is not (15 Nov 2026)

| Page | Data | Notes |
|---|---|---|
| Compare (`/compare`) | Real, from `/comparison` | MODIS, VIIRS and harmonized side by side |
| Analytics (`/analytics`) | Real, from `/comparison` | Anomaly, clusters and month-to-month change show "Unavailable" (they need multi-year data) |
| Explore (`/`) | Demo data | Still California fixtures, labelled "Demo data" |

- The site shows whatever months are in your `data/fires.duckdb` (British Columbia, UTC). A database with only
  July 2023 gives the numbers in this guide; the team's multi-year database (2003, 2010, 2017, 2018, 2021, 2023, 2024)
  works for any month in those years. Months without data show zeros, other regions show an error.
- **Harmonized = identity baseline** (harmonized FRP equals MODIS FRP, one point per match group).
  The Bayesian model in `phase2/algorithm/` is not connected to `model_runs` / `model_predictions` yet.
  The API always uses the newest model run, so once the Bayesian model saves a run there, the site picks it up.

## 1. Requirements

- Python 3.13 and `uv`
- Node.js 22 LTS or newer (`node --version`)
- `data/fires.duckdb` with the BC July 2023 data. The `data/` folder is gitignored, so get it from a
  teammate or build it with Phase 1 and Phase 2 (`docs/phase2_setup.md`).

## 2. One-time setup

```powershell
uv venv --python 3.13
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

UI packages (installs exactly what `package-lock.json` lists and does not change it):

```powershell
cd firesync-app
npm ci
copy .env.example .env
cd ..
```

`.env` should contain `VITE_API_BASE_URL=http://localhost:8000` (no trailing slash). `.env` is gitignored,
never commit it. Without it the UI also falls back to `http://localhost:8000`.

## 3. Fill the harmonized record (once per database)

`model_runs` and `model_predictions` start empty, so the harmonized cards stay at 0 until a model run exists.
Stop the API first if it is running: on Windows DuckDB cannot write while another process has the file open.

```powershell
python -m phase2.phase2_run --only splits --only baseline --no-plots
```

Check the printed table: `model_runs` at least 1, `model_predictions` 6,788 for the BC July 2023 data.
`--only splits` is needed because the default split method (`event`) must exist before the baseline runs.

## 4. Start the API (terminal 1)

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn phase3.api:app --reload --port 8000
```

Wait for `Application startup complete`, then check in the browser:

- `http://localhost:8000/health` shows `"database_found": true` and `"observations": 142051`
- `http://localhost:8000/docs` lists every endpoint
- `http://localhost:8000/comparison?month=2023-07&sample=3` shows:

| Sensor | detections | mean_frp_mw | active_days |
|---|---|---|---|
| MODIS | 24,195 | about 101.6 | 31 |
| VIIRS | 117,856 | about 12.6 | 30 |
| harmonized | 6,788 | about 114.6 | 28 |

`404 Not Found` for `/` and `/favicon.ico` in the log is normal: those pages do not exist.

Optional API settings (environment variables): `PARSEC_DB_PATH` (other database file),
`PARSEC_DEMO=1` (demo database), `PARSEC_CORS_ORIGINS` (allowed UI origins, comma separated, default `*`).

## 5. Start the UI (terminal 2)

Keep the API running and open a second terminal:

```powershell
cd firesync-app
npm run dev
```

Open `http://localhost:5173/compare`. You should see British Columbia, the numbers from the table above,
no "Demo data" badges, and a daily peak on 9 July. Analytics (`/analytics`) with MODIS + VIIRS selected
shows 117,856 detections and a total FRP of about 1,481,756 MW.

The API log shows one line per page load, for example
`GET /comparison?region=british_columbia&month=2023-07&sample=300 ... 200 OK`. That line proves the UI really
asked the API.

## Running with the multi-year database

Nothing in the code changes. Check these three things:

1. `http://localhost:8000/health` shows about 1.9 million observations instead of 142,051.
2. A model run exists: open `/comparison?month=2023-07&sample=3` and look at the harmonized block. If it says
   `no harmonization run yet`, run step 3 once (stop the API first).
3. On Compare, pick July 2023. MODIS and VIIRS should still show 24,195 and 117,856 if the same FIRMS products
   were downloaded. Then try another loaded month, for example August 2023.

## Running in GitHub Codespaces

`localhost` in your browser is not the Codespace, so the UI needs the forwarded address of the API:

1. Start the API (step 4). In the **Ports** tab, right-click port 8000 and set **Port Visibility** to **Public**.
   A private port asks for a GitHub login, which blocks the UI's requests.
2. Copy the forwarded address of port 8000 (it looks like `https://<name>-8000.app.github.dev`) and put it in
   `firesync-app/.env` as `VITE_API_BASE_URL=...` with no trailing slash.
3. Start the UI (step 5) and open the forwarded address of port 5173. If the page does not load, start it with
   `npm run dev -- --host`.
4. Check: the forwarded 8000 address plus `/health` opens in a private browser window without a login.

## 6. Checks before committing UI changes

```powershell
cd firesync-app
npm test            # unit tests (Vitest)
npm run typecheck   # must print no errors
npm run build       # production build into dist/ (gitignored)
cd ..
python phase2_test.py --engineering-only
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Red "Failed to fetch" box in the UI | API not running, or wrong port | Check `http://localhost:8000/health`; start step 4 |
| Requests go to `localhost:5173/comparison` and return HTML | Wrong or missing base URL | Fix `VITE_API_BASE_URL` in `firesync-app/.env`, then restart `npm run dev` (Vite reads `.env` only at start) |
| "blocked by CORS policy" in the browser console | `PARSEC_CORS_ORIGINS` set without the UI origin | Include `http://localhost:5173` exactly; `localhost` and `127.0.0.1` are different origins |
| `API 404: unknown region` | UI asks for a region the API does not know | Use British Columbia; the API regions come from `configs/phase2.yaml` |
| `503 database not found` | API started outside the repo root, or no database | Start uvicorn from the repo root; check `data/fires.duckdb` exists |
| Harmonized shows 0 / "Unavailable" | No model run yet | Step 3, then restart the API and reload the page |
| Pipeline error "being used by another process" | API holds the database file | Stop the API (Ctrl+C), run the pipeline, start the API again |
| "Address already in use" on port 8000 | Another program uses the port | `--port 8001` and set `VITE_API_BASE_URL=http://localhost:8001` |
| `Activate.ps1` or `npm` "running scripts is disabled" | PowerShell execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use `npm.cmd` |
| `node` not recognized | Node.js missing or terminal opened before install | Install Node 22 LTS, open a new terminal |
| Charts flat at 0 while totals are correct | Date format mismatch | Already handled: the UI cuts API dates like `2023-07-01 00:00:00` to `2023-07-01` |

## Known gaps

- Explore still uses demo data.
- `/comparison` returns `daily.date` as `"YYYY-MM-DD 00:00:00"`; the UI handles it, the API could return `YYYY-MM-DD`.
- The Bayesian model (`phase2/algorithm/parsec.c`) produces grid-cell and hour results (`field_posterior.csv`),
  not match-group predictions, so connecting it needs an import step and probably its own screen.
