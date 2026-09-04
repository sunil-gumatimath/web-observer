# Production

Live ops runbook for the deployed stack. Last verified: 2026-09-03 (API rev `00014-qf4`, image `:729ac5b`).

## Live endpoints

| Component | URL |
|---|---|
| Backend API (Cloud Run) | `https://web-observer-api-788773861203.us-central1.run.app` |
| Frontend (Vercel) | `https://web-observer-ted.vercel.app` |
| Health / readiness | `<api>/health`, `<api>/ready`, `<api>/metrics` (no auth) |

## GCP project

- **Project ID:** `project-a9da9837-bf64-4084-924` (number `788773861203`)
- **Region:** `us-central1` (free-tier eligible; `e2-micro` Always-Free only here / `us-west1` / `us-east1`)
- **Billing:** enabled (required even for free-tier usage — stays ~$0 under quotas)
- **Enabled APIs:** `run`, `artifactregistry`, `cloudbuild`, `secretmanager`, `cloudscheduler`

## Architecture

```text
Browser (Vercel frontend)
   │ HTTPS + CORS (single origin)
   ▼
Cloud Run service `web-observer-api` (FastAPI, port 8000, scale-to-zero)
   │  DATABASE_URL ──▶ Neon Postgres (free tier, via Secret Manager)
   │  REDIS_URL ──────▶ Upstash Redis (free tier, via Secret Manager)
   │  snapshots ──────▶ local disk (STORAGE_BACKEND=local, EPHEMERAL — see limits)

Cloud Scheduler (HTTP, OAuth as compute SA) ──▶ Cloud Run Jobs `:run` API
   │  */1  scheduler-tick  ──▶ web-observer-scheduler (one-shot `scheduler_once`, enqueues due checks)
   │  */10 worker-tick     ──▶ web-observer-worker    (dramatiq, queues http_checks+notifications, ≤600s pass)
   │  :05,:15… browser-tick ─▶ web-observer-browser   (dramatiq, queue browser_checks, 2Gi image w/ Chromium)

Cloud Build (`cloudbuild.yaml`) ──▶ Artifact Registry `web-observer` (images `api`, `browser`)
Secret Manager ──▶ all credentials (services AND jobs consume via `--set-secrets …:latest`)
```

Cloud SQL / Memorystore are deliberately **not** used (no free tier). No Compute Engine VMs (count is 0).

## Backend service (`web-observer-api`)

- **Image:** `us-central1-docker.pkg.dev/project-a9da9837-bf64-4084-924/web-observer/api:<sha>` (also tagged `:latest`)
- **Dockerfile:** `backend/Dockerfile` (uvicorn `app.main:app`, port `8000`)
- **Resources:** 1 vCPU, 1Gi RAM, concurrency 80, timeout 300s, `min-instances=0`, `max-instances=3`, CPU throttling on, startup CPU boost
- **Env (plain):** `APP_ENV=production`, `STORAGE_BACKEND=local`, `PYTHONUNBUFFERED=1`, `CORS_ORIGINS=https://web-observer-ted.vercel.app`
- **Env (secrets, `…:latest`):** `DATABASE_URL, REDIS_URL, SECRET_KEY, INTERNAL_API_TOKEN, CLERK_JWKS_URL, CLERK_ISSUER, CLERK_SECRET_KEY, RESEND_API_KEY, LLM_API_KEY, LLM_API_BASE` ← `web-observer-{db,redis,secret,internal,clerk-jwks,clerk-issuer,clerk-secret,resend,llm-key,llm-base}`
- **CORS:** explicit allow-list only. Note: `allow_origin_regex=https://.*\.vercel\.app` (`backend/app/main.py:81`) does **not** actually admit previews (verified by preflight) — every frontend origin must be added to `CORS_ORIGINS`.

## Workers & scheduling

| Job | Command | Trigger |
|---|---|---|
| `web-observer-scheduler` | scheduler one-shot pass | `web-observer-scheduler-tick`, `* * * * *` |
| `web-observer-worker` | `dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2` | `web-observer-worker-tick`, `*/10 * * * *` |
| `web-observer-browser` | `dramatiq app.workers --queues browser_checks --processes 1 --threads 1` (image `browser`, 2Gi) | `web-observer-browser-tick`, `5,15,25,35,45,55 * * * *` |
| `web-observer-migrate` | `alembic upgrade head` | manual only |

**Auth design (important):** Scheduler targets the v2 Jobs API —
`https://run.googleapis.com/v2/projects/<id>/locations/us-central1/jobs/<job>:run` — with an **OAuth** token (`--oauth-service-account-email=<projnum>-compute@developer.gserviceaccount.com`). Google APIs on `*.googleapis.com` expect OAuth, **not** OIDC: the original OIDC-based ticks failed 100% with `401 UNAUTHENTICATED` (fixed 2026-09-03). Do not switch back to OIDC.

**IAM required (already granted):**
- Compute SA + `roles/run.invoker` on each of the 3 worker/scheduler/browser jobs (Scheduler `:run` calls).
- Compute SA + `roles/iam.serviceAccountUser` on itself (Cloud Build deploy step needs `actAs`).

## Database & migrations

- **Postgres:** Neon free tier. Connection string in secret `web-observer-db` (`postgresql+psycopg://…?sslmode=require`). Schema managed by Alembic (`backend/alembic/`); app never runs `create_all` outside dev/test.
- **Current head:** `012_add_ai_intelligence_fields` (semantic_trigger, title/impact/confidence). History: run `alembic upgrade head` via the `web-observer-migrate` job after every backend deploy that touches `backend/alembic/versions/`.
- **Incident 2026-09-03:** prod DB was stamped `012` while the deployed image predated the script → migrate failed with `Can't locate revision`. Fixed by rebuilding from HEAD. Lesson: image and DB must move together (build → deploy → migrate).

## Redis

- **Upstash** free tier, URL in secret `web-observer-redis`. Used for Dramatiq broker, rate limiting, caching. No AUTH issues observed; worker logs show clean connect/process/shutdown cycles.

## Frontend

- Hosted on Vercel (`web-observer-ted`), auto-deploys from git. Talks to the API via `NEXT_PUBLIC_API_BASE_URL`. Only this one origin is allow-listed (ashen + bare `web-observer.vercel.app` were removed from `CORS_ORIGINS`).
- Only `/health`-style public routes are unauthenticated; app routes use Clerk + internal token.

## Build & deploy

Full pipeline (builds **and** deploys API):

```powershell
$sha = git rev-parse HEAD
gcloud builds submit --async --config cloudbuild.yaml \
  --substitutions='_REGION=us-central1' \
  --substitutions='_SERVICE=web-observer-api' \
  --substitutions='_REPO=web-observer' \
  --substitutions="COMMIT_SHA=$sha"
```

Fast path (deploy already-pushed image, preserves env):

```powershell
gcloud run services update web-observer-api --region=us-central1 `
  --image='us-central1-docker.pkg.dev/project-a9da9837-bf64-4084-924/web-observer/api:<sha>'
gcloud run jobs update web-observer-migrate --region=us-central1 --image='<same>'
gcloud run jobs execute web-observer-migrate --region=us-central1 --wait
```

**PowerShell/gcloud.ps1 gotchas (bite repeatedly):**
- Never pass comma-separated lists in one flag (`--set-secrets=a,b`, `--substitutions=a,b`, `--remove-env-vars=a,b`, `--args=a,b` mostly OK but secrets/subs split). Repeat the flag instead: `--set-secrets='K=v' --set-secrets='K2=v2'`.
- `gcloud builds submit` from CLI leaves `$COMMIT_SHA` empty → always pass `COMMIT_SHA=$(git rev-parse HEAD)` explicitly.

## Verify prod (copy-paste)

```powershell
curl.exe -s https://web-observer-api-788773861203.us-central1.run.app/health
curl.exe -s https://web-observer-api-788773861203.us-central1.run.app/ready
curl.exe -s https://web-observer-api-788773861203.us-central1.run.app/metrics
# CORS allow-list check (kept origin gets ACAO header, removed ones don't):
curl.exe -s -D - -o $null -X OPTIONS -H 'Origin: https://web-observer-ted.vercel.app' -H 'Access-Control-Request-Method: GET' https://web-observer-api-788773861203.us-central1.run.app/health
# Scheduler ticks healthy when status.code is empty:
gcloud scheduler jobs describe web-observer-scheduler-tick --location=us-central1 --format='value(status.code, lastAttemptTime)'
gcloud run services logs read web-observer-api --region=us-central1 --limit=30 | Select-String -Pattern '(?i)error|traceback'
```

Healthy baseline (2026-09-03): 22 monitors, ~188 runs/24h, outbox + webhooks pending = 0.

## Known limits / debt

1. **Snapshots are ephemeral** (`STORAGE_BACKEND=local`): `snapshot_text_storage_miss … falling_back_to_db_preview_snapshot` warnings are expected; files vanish on redeploy. Move to GCS if snapshot durability matters.
2. **Artifact Registry is ~3.2 GB vs 0.5 GB free quota** — prune old digests (`gcloud artifacts docker images delete …`) or expect a small charge.
3. `GET /api/v1/public/assets/…/logo.svg → 404` — missing brand asset (cosmetic).
4. No staging environment; `cloudbuild.yaml` deploys straight to prod on submit.
5. `infra/gcp/service-api.yaml` + `infra/gcp/jobs.yaml` describe intent; live state was finished by hand (OAuth ticks, migrate job, secret set) — reconcile before using `services replace`.
