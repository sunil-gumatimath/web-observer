<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Free hosting (Vercel + Fly.io / GCP / Upstash + Neon)

Stack: `FastAPI + Neon Postgres + Upstash Redis/Dramatiq + Next.js + Clerk + Resend + Playwright + local disk`. 100% free tier.

## 1-click summary

| Layer | Host | Why |
|-------|------|-----|
| **Frontend :3000** | **Vercel Hobby** | Native Next.js, no sleep |
| **API + Workers + Scheduler + Playwright** | **Fly.io** `backend/fly.toml` | 4 processes, persistent volumes, Playwright deps built-in |
| **Redis broker** | **Upstash Redis Free** | `rediss://` TLS, 10k cmds/day |
| **Postgres** | **Neon Free** | You already use Neon |
| **Alt one-click** | **Render** `render.yaml` Blueprint | `dashboard.render.com` → Blueprint → Apply (api sleeps after 15m) |
| **GCP Free** | **Google Cloud** `cloudbuild.yaml` + `infra/gcp/` | Cloud Run free 2M req + e2-micro Always Free VM — see GCP section below |

## Vercel (frontend) — 2 min

1. Import repo at `vercel.com/new` → Root = `frontend`.
2. Env (Vercel → Settings → Environment Variables):
   ```
   NEXT_PUBLIC_API_BASE_URL=https://web-observer-api.fly.dev
   NEXT_PUBLIC_INTERNAL_API_TOKEN=dev-internal-token  # not needed in prod, keep empty
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
   CLERK_SECRET_KEY=sk_live_...
   ```
3. Deploy. Frontend at `https://web-observer.vercel.app`.

## Upstash Redis — 1 min

1. `console.upstash.com` → Create Redis (Global) → Copy `rediss://default:...@...:6379`.
2. Use as `REDIS_URL` for Fly/Render.

## Fly.io (backend) — 5 min

```powershell
# one-time
npm i -g flyctl   # or: powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
fly auth login
cd backend
fly launch --name web-observer-api --region bom --no-deploy

# optional 1GB disk for snapshots (brand-assets/screenshots) — free tier includes 3GB
fly volumes create data --region bom --size 1 --yes
# then uncomment [[mounts]] in backend/fly.toml and add env STORAGE_PATH=/data

fly secrets set `
  DATABASE_URL="postgresql+psycopg://USER:PASS@ep-xxx.neon.tech/neondb?sslmode=require" `
  REDIS_URL="rediss://default:PASS@xxx.upstash.io:6379" `
  SECRET_KEY="32+random-chars-pin-this" `
  INTERNAL_API_TOKEN="pin-this-too" `
  CLERK_JWKS_URL="https://YOUR-INSTANCE.clerk.accounts.dev/.well-known/jwks.json" `
  CLERK_ISSUER="https://YOUR-INSTANCE.clerk.accounts.dev" `
  CLERK_SECRET_KEY="sk_live_..." `
  RESEND_API_KEY="re_..." `
  APP_ENV="production"

fly deploy
fly status   # api/worker/browser/scheduler should be started
fly logs --process api
```

Test: `https://web-observer-api.fly.dev/health`, `/ready`, `/docs`.

**Free tier note:** Fly free allowance is 3× `shared-cpu-1x 256MB` VMs. `backend/fly.toml` uses `512/1024MB` — within the $5/mo free credit, stays free. Set `auto_stop_machines="stop"` to save hours if traffic is low.

## Render (alternative, no flyctl)

1. `dashboard.render.com` → New → Blueprint → Connect `web-observer` repo → Apply `render.yaml`.
2. Dashboard → Each service → Environment → Add `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `INTERNAL_API_TOKEN`, `CLERK_*`, `RESEND_API_KEY`.
3. Render auto-deploys `api` (health `/health`), `worker`, `browser`, `scheduler`.

> Render free web service sleeps after 15m; next `Fetch`/`Run now` will cold-start (~30s). Fly keeps warm.

## Neon

No change — just set `DATABASE_URL` in Fly/Render secrets. Run migrations once:

```powershell
cd backend
$env:DATABASE_URL="postgresql+psycopg://..."  # your Neon URL
alembic upgrade head
```

## Local disk snapshots

* **Fly with volume:** mount to `/data` and set `STORAGE_PATH=/data` (recommended).
* **Render free (no disk):** snapshots are ephemeral — `brand-assets/` resets on deploy. For persistence without volume, switch to `STORAGE_BACKEND=s3` + Cloudflare R2 free tier (10GB).

## Google Cloud Free Tier (alternative to Fly)

GCP gives `$300 trial` + Always Free: `e2-micro` (1 vCPU/1GB `us-central1` Always Free) + Cloud Run 2M req free. Playwright needs `1-2Gi` so pick one:

**A) Single e2-micro VM (Always Free, simplest — keeps `docker-compose.yml` 1:1):**
```powershell
gcloud compute instances create web-observer-vm --machine-type=e2-micro --zone=us-central1-a --image-family=cos-stable --image-project=cos-cloud --tags=http-server
gcloud compute scp --zone us-central1-a ./docker-compose.yml web-observer-vm:~/
gcloud compute ssh --zone us-central1-a web-observer-vm -- "docker compose up -d --build"
# set .env on VM with DATABASE_URL (Neon) + REDIS_URL (rediss://humorous-vulture-...) + SECRET_KEY...
```

**B) Cloud Run (serverless, auto-scale to 0):**
```powershell
# one-time: enable APIs + create Artifact Registry + secrets
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create web-observer --repository-format=docker --location=us-central1
gcloud secrets create web-observer-db --data-file=- <<< "postgresql+psycopg://..."
gcloud secrets create web-observer-redis --data-file=- <<< "rediss://default:...@humorous-vulture-154883.upstash.io:6379"

# deploy via Cloud Build (push to main auto-deploys)
gcloud builds submit --config cloudbuild.yaml --substitutions=_REGION=us-central1,_SERVICE=web-observer-api,_REPO=web-observer
# or: gcloud run deploy web-observer-api --image us-central1-docker.pkg.dev/PROJECT/web-observer/api:latest --region us-central1 --allow-unauthenticated --port 8000 --memory 1Gi --set-secrets DATABASE_URL=web-observer-db:latest,REDIS_URL=web-observer-redis:latest

# workers as Cloud Run Jobs (free) — see infra/gcp/jobs.yaml
gcloud run jobs create web-observer-worker --image us-central1-docker.pkg.dev/PROJECT/web-observer/api:latest --region us-central1 --command "dramatiq" --args "app.workers,--queues,http_checks notifications,--processes,1,--threads,2" --memory 1Gi
gcloud run jobs create web-observer-browser --image us-central1-docker.pkg.dev/PROJECT/web-observer/browser:latest --region us-central1 --command "dramatiq" --args "app.workers,--queues,browser_checks,--processes,1,--threads,1" --memory 2Gi
```
Files: `cloudbuild.yaml` (builds `backend/Dockerfile` + `Dockerfile.browser` → push → `gcloud run deploy`), `infra/gcp/service-api.yaml` (Knative Service), `infra/gcp/jobs.yaml` (worker/scheduler notes). Cloud Run is ephemeral — use `STORAGE_BACKEND=s3` + GCS bucket `gs://web-observer-snapshots` (5GB free) instead of local disk.

## Check after deploy

```
Frontend: https://web-observer.vercel.app/dashboard
API Fly:  https://web-observer-api.fly.dev/docs
API GCP:  https://web-observer-api-...-uc.a.run.app/docs
Health:   /health 200 + /ready 200 (DB reachable)
Run:      Create monitor → Run now → first success = baseline
```

Need me to run `fly launch`/`gcloud` for you? Share a Fly personal token (`fo1_...` via `fly auth token`) or GCP `gcloud auth` and I can deploy.
