# PARSEC / FireSync

Read [START_HERE.md](START_HERE.md) for setup, safe Git application, demo startup and limitations. The audit findings and test evidence are in [docs/REPOSITORY_AUDIT.md](docs/REPOSITORY_AUDIT.md) and [docs/REPAIR_TEST_RESULTS.md](docs/REPAIR_TEST_RESULTS.md).

Run every offline check with one command:

```bash
python run_tests.py --install
```

Use `python run_tests.py` on subsequent runs. Python 3.12, Node.js 24 LTS and GCC were used for verification. Tests do not require NASA credentials.

The harmonized engineering view defaults to an identity baseline. The separate Bayesian mask preview is exploratory, uses illustrative parameters and has no validated physical FRP accuracy. Missing data remains unknown.

---

## Scientific Background
### MODIS 
**MODIS (Moderate Resolution Imaging Spectroradiometer)**
Is an Earth-observing instrument aboard NASA's **Terra** and **Aqua** satellites.
It is widely used of monitoring several land resources apart from fire.
Method of detection for thermal anomaly detection is to compare neighbouring pixels to identify degree of thermal discharge.
The standard product has a spatial resolution of approximately **1km**.
MODIS provides one of longest satellie based fire activity records.

### VIIRS
**VIIRS (Visible Infrared Imagining Radiometer Suite)**
Is a newer generation Earth-observing  intrument on **Suomi NPP, NOAA-20 and NOAA-21**.
It detects fire/thermalactivity on global scale , in a similar fashion as to MODIS.
The standard product has a spatial resolution of approximately **375m**.
VIIRIS gives a better representation of large fire perimeters.

### The MODIS-VIIRS Harmonization Problem
Central to this is an Harmonization Problem , which stems from the difference in size of spatial resolution;
i.e. MODIS-----> 1km vs. VIIRS-----> 375m
Some other key issues are :-
- **Spatial sensitivity:** VIIRS can detect smaller and weaker thermal anomalies.
- **Spectral response:** They use different spectral bands and detector charactristics.
- **Detection algorithm:** fire classifications thresholds and tests are not identical.
- **Observation timing:** different satellites may have different times of observation over the same geographical region.
- **Measurement uncertainity:** different sensors have different confidence and intesity estimates.

# Phase 1 

## Setup

1. Get a [FIRMS MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/map_key/) and save it as a GitHub Codespaces secret named `FIRMS_MAP_KEY`, scoped to this repository. Restart your Codespace after adding it.
2. Run: `python -m pip install -r requirements.txt`
3. Run the demo: `python phase1_run.py`. No API key or NASA network call is needed.
4. Run real test data: `python phase1_run.py --real --start 2023-07-01 --end 2023-07-05`.
5. Run July 2023: `python phase1_run.py --real`.
6. View all flags: `python phase1_run.py --help`.

# Phase 2 — engineering and scientific harmonization

Phase 1 stays at the repository root with its original files and commands. Phase 2
modules live in `phase2/`; the independent scientific engine lives in
`phase2/algorithm/`. Its C source and all its original Python scripts are unchanged.

## Quick start (from repository root)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python phase1_run.py
python phase2_test.py
python phase2_run.py --demo --no-plots
```

`phase2_test.py` remains a legacy Phase 2-only entry point. Use `run_tests.py` for Phase 1, Phase 2, Phase 3/API, model preview, C and frontend checks.
`phase2_run.py --demo` seeds a fresh synthetic Phase 2 fixture, runs the engineering
pipeline and runs the independent algorithm offline. Neither touches the real database.
The C stress-test warning is retained and does not certify numerical scalability.

## Real workflows

```bash
python phase1_run.py --real --start 2023-07-01 --end 2023-07-31
python phase2_run.py --start 2023-07-01 --end 2023-07-31
```

The latter runs the engineering pipeline and identity baseline, not the C field model.
For an end-to-end run including exploratory NASA mask harmonization:

```bash
python phase2_run.py --start 2023-07-01 --end 2023-07-31 --nasa-csv-dir /absolute/path/to/extracted --max-folds 4
```

To test the algorithm independently of the engineering work:

```bash
python phase2_test.py --algorithm-only
python phase2_test.py --algorithm-only --nasa-csv-dir /absolute/path/to/extracted --max-folds 4
```

If you have no extracted NASA science pixels:

```bash
python phase2_test.py --algorithm-only --nasa-live --install --max-folds 4
```

Earthdata credentials are required for live Level-2 downloads; a FIRMS MAP_KEY is
not interchangeable with Earthdata login. A FIRMS hotspot CSV is not a Level-2 mask CSV.

See [Phase 2 setup](docs/phase2_setup.md), [organization and testing](docs/REPOSITORY_ORGANIZATION.md),
[scientific input contract](phase2/algorithm/REAL_DATA_CONTRACT.md), and
[original independent algorithm report](docs/ALGORITHM_TEST_REPORT.md).


- Observation coverage (Task 2.8): see [docs/phase2_coverage.md](docs/phase2_coverage.md)
