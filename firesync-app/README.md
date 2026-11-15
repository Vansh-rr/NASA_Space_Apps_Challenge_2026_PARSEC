# FireSync — Wildfire Monitoring & Analytics

FireSync is a web application for exploring historical wildfire activity using satellite fire detection data.

Built for the **NASA Space Apps Challenge 2026 — PARSEC**, FireSync helps users visualize fire observations, analyze fire activity, compare satellite sensors, and export fire data.

## Features

| Feature | Description |
|---|---|
| Explore | View fire detections on an interactive map and explore monthly fire activity. |
| Analytics | Analyze fire statistics, historical trends, and anomalies. |
| Compare | Compare fire detection information from MODIS and VIIRS. |
| Download | Export fire observations, fire history, fire analytics, and burning activity calendars as CSV files. |
| Interactive Charts | Visualize fire detections, historical activity, and anomaly scores. |

## Technology Stack

**Frontend**
- React
- TypeScript
- Vite
- MapLibre GL JS
- Recharts
- CSS Modules

**Backend**
- Python
- FastAPI
- Uvicorn
- DuckDB

---

# 1. Getting Started

Follow these instructions to install and run FireSync on your computer.

## Step 1 — Prerequisites

Before starting, install the following software:

| Software | Purpose | Download |
|---|---|---|
| Node.js (LTS) | Run the frontend and install JavaScript packages | https://nodejs.org/ |
| Python 3 | Run FastAPI and data processing | https://www.python.org/downloads/ |
| Git | Clone the GitHub repository | https://git-scm.com/downloads |
| Visual Studio Code | Recommended code editor | https://code.visualstudio.com/ |

Verify your installations by opening a terminal and running:

```bash
node --version
npm --version
python --version
git --version
```

If the commands display version numbers, the software is installed.

**Windows PowerShell users:** If `npm` is blocked by the PowerShell execution policy, use `npm.cmd` instead of `npm` in the commands below.

## Step 2 — Clone the GitHub Repository

Open a terminal and run:

```bash
git clone <REPOSITORY_URL>
```

Replace `<REPOSITORY_URL>` with the official PARSEC GitHub repository URL.

Navigate into the downloaded project:

```bash
cd NASA_Space_Apps_Challenge_2026_PARSEC
```

If your downloaded folder has a different name, use that folder name instead.

**Important:** The following installation commands must be executed from the main repository folder containing `requirements.txt`, `phase1_run.py`, `phase2_run.py`, `firesync-app/`, and the root `package.json`.

## Step 3 — Install Dependencies

Install the Python backend dependencies:

```bash
python -m pip install -r requirements.txt
```

Install the main development dependencies:

```bash
npm install
```

Install the React frontend dependencies:

```bash
npm --prefix firesync-app install
```

Windows PowerShell users can replace `npm` with `npm.cmd`.

Once the installation completes, you can proceed to database setup.

---

# 2. Database Setup

FireSync uses DuckDB to store fire observations and processed fire activity information.

The application supports a **demonstration mode** for local testing and a real-data workflow for historical satellite observations.

## Step 1 — Create the Demo Database

From the repository root, run:

```bash
npm run setup:demo
```

Then run the demonstration processing pipeline:

```bash
python phase2_run.py --demo --no-plots
```

The Phase 2 command creates a new demonstration processing workspace. It is not a command for updating individual stages inside an existing database.

The demo database is expected at:

```text
data/demo_fires.duckdb
```

## Step 2 — Verify the Database File

On Windows PowerShell:

```powershell
Test-Path .\data\demo_fires.duckdb
```

Expected result:

```text
True
```

If the result is `False`, check the output of the database setup commands before continuing.

**Note:** The supplied demo database contains only a small number of synthetic observations. Some historical analytics, anomalies, and calendar results may be empty or unavailable.

---

# 3. Running FireSync

## Recommended — Start Frontend and Backend Together

From the main repository folder, run:

```bash
npm run dev:demo
```

Windows PowerShell:

```powershell
npm.cmd run dev:demo
```

This command starts:

1. The React frontend through Vite.
2. The Python FastAPI backend in demonstration mode.

Keep the terminal running while using FireSync.

### Application URLs

| Service | URL |
|---|---|
| FireSync Web Application | http://localhost:5173 |
| FastAPI Documentation | http://localhost:8000/docs |
| Backend Health Check | http://localhost:8000/health |

Open **http://localhost:5173** in your browser to use FireSync.

**Important:** The local FastAPI development server uses `http://`, not `https://`, unless HTTPS has been configured separately.

## Alternative — Start Services Separately

If the combined command does not work, open two terminals.

**Terminal 1 — FastAPI Backend**

From the main repository folder:

Windows PowerShell:

```powershell
$env:PARSEC_DEMO = "1"
python -m uvicorn phase3.api:app --reload --port 8000
```

**Terminal 2 — React Frontend**

Navigate into the frontend folder:

```bash
cd firesync-app
```

Start Vite:

```bash
npm run dev
```

Both terminals must remain running.

---

# 4. Verify the Backend Connection

Before testing the application, check that FastAPI can access the database.

Open:

http://localhost:8000/health

A successful response may look like:

```json
{
  "status": "ok",
  "database": "demo_fires.duckdb",
  "database_found": true,
  "database_connected": true,
  "demo": true,
  "observations": 2
}
```

The observation count may vary depending on the database contents.

### What the response means

- `status: "ok"` — the health check succeeded.
- `database_found: true` — the database file exists.
- `database_connected: true` — FastAPI can connect to the database.
- `demo: true` — demonstration mode is active.
- `observations` — number of observation records available.

If the health check is successful, open the FireSync website.

**Note:** A successful health check does not necessarily mean all historical analytics tables are populated.

---

# 5. Using the FireSync Application

## Explore

The Explore page allows users to:

- View fire detections on an interactive map.
- Select regions and available date ranges.
- Explore monthly burning activity.
- Inspect fire observation information.

## Analytics

The Analytics page provides:

- Fire activity statistics.
- Historical fire trends.
- Monthly fire detection information.
- Anomaly information where sufficient historical data is available.
- Interactive charts.

## Compare

The Compare page allows users to examine fire detection differences between supported satellite sensors, including MODIS and VIIRS.

Sensor comparisons should follow the project's documented methodology. Raw detection counts from different sensors should not automatically be treated as equivalent.

## Download

The Download page provides four CSV export options:

| Export | Description |
|---|---|
| Fire Observations CSV | Fire detection records, including available observation coordinates and FRP information. |
| Fire Activity History CSV | Historical monthly fire detection activity. |
| Fire Analytics CSV | Monthly statistics, historical reference values, and available anomaly information. |
| Burning Activity Calendar CSV | Monthly fire activity with available historical classifications and percentiles. |

Users can select supported regions, sensors, and dates before exporting data.

The page also provides a fire analytics graph.

**Data limitations:**

- Exports depend on available backend records.
- Observation exports may be limited by the API's maximum returned records.
- Some anomaly statistics require multiple years of historical data.
- Missing observations do not always mean zero fire activity.
- The demo database is intended for functionality testing, not scientific conclusions.

---

# 6. Using Real Satellite Data

The official PARSEC repository includes processing workflows for satellite fire detection data.

The general workflow is:

1. Configure the required data sources and credentials.
2. Obtain supported satellite fire observations.
3. Run the Phase 1 ingestion workflow.
4. Run the Phase 2 processing workflow.
5. Verify the processed DuckDB database.
6. Start the backend in normal mode.
7. Open FireSync to explore and export the available records.

For the real database, start the application with:

```bash
npm run dev
```

Unlike `dev:demo`, this command does not enable demonstration mode.

Real-data setup may require additional configuration. Refer to the repository's Phase 1 and Phase 2 documentation before running the full ingestion and processing pipeline.

---

# 7. Project Structure

```text
NASA_Space_Apps_Challenge_2026_PARSEC/
│
├── package.json
├── requirements.txt
├── README.md
│
├── phase1_run.py
├── phase2_run.py
│
├── phase3/
│   └── api.py
│
├── data/
│   └── demo_fires.duckdb
│
└── firesync-app/
    │
    ├── package.json
    ├── .env.example
    │
    └── src/
        │
        ├── app/
        │   └── App.tsx
        │
        ├── pages/
        │   ├── ExplorePage.tsx
        │   ├── AnalyticsPage.tsx
        │   ├── ComparePage.tsx
        │   ├── DownloadPage.tsx
        │   └── DownloadPage.module.css
        │
        ├── components/
        │   ├── layout/
        │   ├── map/
        │   ├── search/
        │   ├── activity/
        │   ├── filters/
        │   ├── metrics/
        │   ├── charts/
        │   └── compare/
        │
        ├── services/
        │   ├── api.ts
        │   ├── fireData.ts
        │   ├── analyticsService.ts
        │   ├── comparisonService.ts
        │   └── downloadService.ts
        │
        ├── utils/
        │   ├── downloadCsv.ts
        │   └── fireDownloadAnalytics.ts
        │
        ├── hooks/
        ├── data/
        ├── types/
        └── styles/
```

*The database file is generated locally and is not necessarily included in the GitHub repository.*

---

# 8. Troubleshooting

### Problem: `npm.ps1 cannot be loaded`

Windows PowerShell is blocking the npm PowerShell script.

Use:

```powershell
npm.cmd run dev:demo
```

You can also use `npm.cmd` for other npm commands.

### Problem: `Could not read package.json`

You are likely running the command from the wrong folder.

Navigate to the repository root and check that `package.json` exists.

```powershell
dir package.json
```

### Problem: `'concurrently' is not recognized`

Install the root dependencies:

```powershell
npm.cmd install
```

Then retry:

```powershell
npm.cmd run dev:demo
```

### Problem: `API 503: database not found`

The backend cannot find its configured database.

Check:

```powershell
Test-Path .\data\demo_fires.duckdb
```

If it does not exist, complete the database setup in Section 2.

Restart the application afterward.

### Problem: `/health` works but no Download data appears

A successful health response confirms that the database is accessible, not that all required data is available.

Check the following:

1. The selected region and sensor match the database records.
2. The selected date range contains observations.
3. The API endpoints return records.
4. The historical processing tables have been generated.

You can inspect the available API endpoints at:

http://localhost:8000/docs

### Problem: `no history yet: run phase2_run --only history --only analytics`

The historical analytics tables are missing or unavailable.

The demo pipeline may need to be completed. For partial processing, refer to the Phase 2 module's supported commands rather than using `--demo --only` with the top-level `phase2_run.py`.

A demo database containing only a few records may still lack sufficient history for anomaly calculations.

### Problem: Download buttons are disabled

Possible causes include:

- No records for the selected period.
- The backend is not running.
- The request failed.
- Required historical analytics are unavailable.

Check the backend connection, browser developer console, and selected filters.

---

# 9. Build and Test

For frontend development, navigate into `firesync-app`:

```bash
cd firesync-app
```

Run the automated tests:

```bash
npm test
```

Run TypeScript type checking if configured:

```bash
npm run typecheck
```

Build the production frontend:

```bash
npm run build
```

Preview the compiled frontend:

```bash
npm run preview
```

The production frontend also needs access to a running backend for API-powered features.

---

# 10. Development Notes

- Keep the frontend and backend API contracts consistent.
- Do not commit API keys, passwords, or private credentials.
- Do not commit generated DuckDB databases unless the team explicitly decides to distribute an approved example database.
- Clearly distinguish demonstration data from real satellite observations.
- Preserve missing-data and insufficient-baseline indicators in analytics.
- Keep API configuration in the appropriate environment files.
- Test the Download CSV functionality whenever API response formats change.

---

# Quick Start — Windows PowerShell

For developers who have already installed Python, Node.js and Git:

```powershell
# 1. Clone repository
git clone <REPOSITORY_URL>

# 2. Open project folder
cd NASA_Space_Apps_Challenge_2026_PARSEC

# 3. Install Python dependencies
python -m pip install -r requirements.txt

# 4. Install Node.js dependencies
npm.cmd install
npm.cmd --prefix firesync-app install

# 5. Set up demo data
npm.cmd run setup:demo
python phase2_run.py --demo --no-plots

# 6. Start application
npm.cmd run dev:demo
```

Open **http://localhost:5173**.

To check the backend, visit **http://localhost:8000/health**.

**FireSync — NASA Space Apps Challenge 2026 | PARSEC Team**
