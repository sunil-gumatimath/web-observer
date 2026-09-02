<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Free hosting (Vercel + Fly.io + Upstash + Neon)

Stack: `FastAPI + Neon Postgres + Upstash Redis/Dramatiq + Next.js + Clerk + Resend + Playwright + local disk`. 100% free tier, no Docker Compose on host.

## 1-click summary

| Layer | Host | Why |
|-------|------|-----|
| **Frontend :3000** | **Vercel Hobby** | Native Next.js, no sleep |
| **API + Workers + Scheduler + Playwright** | **Fly.io** `backend/fly.toml` | 4 processes, persistent volumes, Playwright deps built-in |
| **Redis broker** | **Upstash Redis Free** | `rediss://` TLS, 10k cmds/day |
| **Postgres** | **Neon Free** | You already use Neon |
| **Alt one-click** | **Render** `render.yaml` Blueprint | `dashboard.render.com` → Blueprint → Apply (api sleeps after 15m) |

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

## Check after deploy

```
Frontend: https://web-observer.vercel.app/dashboard
API:      https://web-observer-api.fly.dev/docs
Health:   /health 200 + /ready 200 (DB reachable)
Run:      Create monitor → Run now → first success = baseline
```

Need me to run `fly launch` for you? Share a Fly/Upstash token and I can deploy.
