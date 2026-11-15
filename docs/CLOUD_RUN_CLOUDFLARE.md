# Publish FireSync on Cloud Run and Cloudflare Pages

## Prepared repository configuration

The backend uses the root `Dockerfile`, runtime-only `requirements-api.txt` and the tested dependency constraints. Python 3.12 matches the verified API environment. The container runs as a non-root user, listens on Cloud Run's `PORT`, serves the immutable database snapshot read-only, and starts with browser cross-origin access disabled. Only the API modules, config, published preview and `data/fires.duckdb` enter the upload context. Git history, credentials, tests, frontend dependencies and other data are excluded by explicit `.gcloudignore` and `.dockerignore` allowlists.

The frontend uses Node 24, with `firesync-app/.node-version`. Pages builds fail early when the production API URL is absent, points to localhost, or is not an HTTPS origin. Explicit Pages route rewrites support direct links to `/about`, `/compare`, `/analytics` and `/model-preview`.

`requests` is included in the API dependencies because the observations query imports the bounding-box validator from `phase1_downloader`. GCC, GeoPandas, NetCDF and scientific inference dependencies are not needed in the serving image. The published model preview is read-only; this container does not run new inference.

No live URL is recorded until deployment and smoke checks succeed. Deployment requires an authenticated Google Cloud session, a project linked to the existing billing account, Cloudflare GitHub access and the real database snapshot. A billing account alone does not create or configure the project.

## 1. Use the connected branch and prepare the real database

These commands target `ui-backend-connect`. Run them on the laptop or Codespace that actually contains `data/fires.duckdb`.

```bash
git switch ui-backend-connect
git pull --ff-only origin ui-backend-connect
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-api.txt -c requirements-tested.txt
python tools/preflight_deploy.py
```

On PowerShell, activate with `.venv\Scripts\Activate.ps1` instead. The Python deployment helpers work in both shells. Google Cloud CLI, Git and the Cloudflare dashboard remain separate prerequisites.

The preflight requires both sensors for the frontend's default BC/July 2023 selection, a compatible non-synthetic engineering model run with predictions, current history tables, a valid published preview, and a self-contained database without a WAL. It does not download observations, invent a model run, or rewrite a database. Rebuild old derived versions using the current Phase 2 config before deploying. If necessary install the full `requirements.txt` for local preprocessing; only runtime requirements enter the image.

Copy a completed, checkpointed snapshot to `data/fires.duckdb`. Close writers first. The file stays ignored by Git and is deliberately included in the private Google build/container context. It is not served as a downloadable static asset. Updates to observations/model outputs require a new snapshot and backend deployment. Keep external processing separate from this read-only service.

To inspect upload contents before sending anything:

```bash
gcloud meta list-files-for-upload
```

Confirm `data/fires.duckdb`, `Dockerfile`, `requirements-api.txt`, `requirements-tested.txt`, the API modules, config and published preview are listed. Credentials and raw acquisitions should not appear.

## 2. Select your Google Cloud project

Use your actual project ID. Do not use the display name and do not assume `parsec-firesync` is available globally.

```bash
gcloud auth login
gcloud projects list
gcloud billing projects describe YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project YOUR_PROJECT_ID
```

If you do not have a project, create one in Google Cloud Console, link your billing account to it, then use its ID. Source deployment needs the documented deployer/service-account permissions; a paid billing account alone does not grant these. Depending on account setup, the builder identity needs `roles/run.builder`; the deployer needs source-deployment permissions and permission to use the service identity. Do not grant organization-wide Owner roles or commit service-account keys to work around an IAM error. Check the precise denied permission in any returned error.

A dry run prints the scoped command without installing, authenticating, uploading, or creating resources:

```bash
python tools/deploy_cloud_run.py --project YOUR_PROJECT_ID --dry-run
```

Deploy the backend before the Pages URL is known:

```bash
python tools/deploy_cloud_run.py --project YOUR_PROJECT_ID
```

The default region is `europe-west1`, service `parsec-api`, memory `1Gi`, CPU `1`, minimum instances `0`, maximum instances `1`, and request concurrency `4`. Override the project/service/region explicitly when needed. The helper checks the database first, deploys from this directory, reads the service URL and smoke-tests all API views. The URL/result is saved in ignored `deployment.local.json`. CORS remains closed to browser origins until the site URL is supplied. Direct `/health` checks still work.

This command creates billable cloud resources, including build/artifact storage. Scaling limits do not impose a hard spending cap. Configure any desired billing alerts in your own Google Cloud account.

## 3. Connect Cloudflare Pages to GitHub

Create a Git-connected Pages project in the Cloudflare dashboard. Authorize access to `Vansh-rr/NASA_Space_Apps_Challenge_2026_PARSEC`. Set:

| Setting | Value |
| --- | --- |
| Production branch | `ui-backend-connect` |
| Framework preset | React (Vite) |
| Root directory | `firesync-app` |
| Build command | `npm run build` |
| Output directory | `dist` |
| `NODE_VERSION` | `24` |
| `VITE_API_BASE_URL` | Actual HTTPS Cloud Run service URL, without a trailing slash |

Pages installs dependencies from the committed npm lockfile. Use its current build image. The API URL is public configuration compiled into the frontend; it must not be a token or key. `VITE_*` values are visible to site visitors. Never put Google/Earthdata/FIRMS credentials there.

Record the actual production `https://NAME.pages.dev` URL after the build. The initial site will not read API responses until the next CORS step. This is deliberate. A Pages preview deployment on a different hostname is a different origin and is not implicitly authorized.

## 4. Restrict CORS to the actual production site

```bash
python tools/deploy_cloud_run.py --project YOUR_PROJECT_ID --cors-only --frontend-origin https://YOUR_NAME.pages.dev
```

This updates only the service environment, without uploading/building the database again, and verifies both the allowed origin and rejection of an unrelated origin. It also preserves other existing service environment values. CORS controls browser reads; it is not API authentication. The service remains an explicitly public read-only API.

You can run the checks again directly:

```bash
python tools/smoke_api.py --api-url https://YOUR_SERVICE_URL --frontend-origin https://YOUR_NAME.pages.dev
```

Use your exact production origin. If a custom domain is added, update the intended origin and rebuild the frontend if the API URL changes. Changing CORS does not require rebuilding Pages; changing `VITE_API_BASE_URL` does.

## 5. Record verified links and publish the repository entry

```bash
python tools/record_live_demo.py --frontend-url https://YOUR_NAME.pages.dev --api-url https://YOUR_SERVICE_URL
git add README.md
git commit -m "Add verified FireSync live demo URLs"
git push origin ui-backend-connect
```

The helper first checks the API, real/demo provenance, restricted CORS and the frontend's `/compare` HTML route, then replaces the README live-demo block with real links. It refuses malformed URLs and does not use a guessed hostname. Review browser-rendered numbers and open `/compare` directly before submission.

Set the repository website field after the URL is known, using the GitHub About gear or an authenticated GitHub CLI:

```bash
gh repo edit Vansh-rr/NASA_Space_Apps_Challenge_2026_PARSEC --homepage https://YOUR_NAME.pages.dev
```

After the live deployment is verified, merge `ui-backend-connect` into `main` through a reviewed pull request. Then change the Pages production branch to `main` and confirm its deployment works before submitting that live URL. Merging was not performed as part of preparing this hosting configuration.

## Tests and CI

```bash
python run_tests.py --install
```

This includes deployment-command, URL/CORS, database-preflight and upload-allowlist tests. `.github/workflows/cloud-run-container.yml` separately builds the actual Docker image using a generated synthetic test database, runs it with `PARSEC_DEMO=1`, and verifies API routes, preview and restricted CORS. It never accesses Google Cloud or deploys real data. The regular workflow still tests the entire repository and frontend build.

A correct local container test with your real snapshot is:

```bash
docker build -t parsec-api .
docker run --rm -p 8080:8080 -e PARSEC_CORS_ORIGINS=https://YOUR_NAME.pages.dev parsec-api
```

Run the smoke checker from a second terminal against `http://localhost:8080` with the same frontend origin. Docker availability is required for this optional local image test.

## Official references

- [Cloud Run source deployment and required setup](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Google Cloud upload ignore syntax and file-list command](https://docs.cloud.google.com/sdk/gcloud/reference/topic/gcloudignore)
- [Cloudflare Pages build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/)
- [Cloudflare Pages runtime version overrides](https://developers.cloudflare.com/pages/configuration/build-image/)
- [Cloudflare Pages redirect rules](https://developers.cloudflare.com/pages/configuration/redirects/)
