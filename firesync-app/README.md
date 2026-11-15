# FireSync frontend

React + TypeScript + Vite interface for the PARSEC read-only API. Run commands from this directory:

```bash
npm ci
npm run dev
```

The API defaults to `http://localhost:8000`. Set `VITE_API_BASE_URL` in an untracked `.env.local` if needed. See `.env.example`. A relative URL such as `/api` is supported with a reverse proxy. Keep NASA keys and Earthdata credentials on the backend.

Explore uses `/activity` and paginated `/observations`. Compare and Analytics use `/comparison`, including deterministic map samples. Model Preview uses `/model-preview/*`, including all field pages within the actual preview bounds. Missing activity dates/FRP remain null and render as gaps. Detection markers are points, not pixel footprints or burned area. Demo provenance is preserved in badges and map popups.

The default harmonized engineering run is the identity baseline. The independent Bayesian mask preview uses illustrative parameters. Neither view establishes superiority over NASA products. About describes the implemented prototype and its limits.

```bash
npm test
npm run build
```

For the complete Python, API, C and frontend test workflow, use `python run_tests.py --install` from the repository root. See `../START_HERE.md` for demo startup and Git instructions, and `../docs/REPOSITORY_AUDIT.md` for the repairs. External basemap tiles require browser network access. The bundled place search is a fixed demo catalogue; coordinates can be entered directly. A production geocoding provider, authentication, alerts and download UI are not implemented.
