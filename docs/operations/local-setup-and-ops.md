# Local Setup & Ops Plan

Status: **Local development** in one of two supported topologies:

1. **Native processes** — the 5-process launcher (`scripts/restart-stack.ps1`) or manual
   processes (see [docs/local-dev.md](../local-dev.md)).
2. **Docker Compose** — the whole stack (Redis, API, both Dramatiq workers, scheduler,
   frontend) as containers via `docker compose up -d --build` from the repo root
   (`docker-compose.yml`). Postgres stays external (Neon) via `backend/.env`.

Cloud deployment/hosting configuration (Cloud Run, Cloud Build, Render, Vercel) has not
been configured — see the last section.

## Local development

| Service | Native | Docker |
| --------- | --------------------------------------- | --------------------- |
| `postgres` | Neon URL or local Postgres (`DATABASE_URL`) | same (external) |
| `redis` | `localhost:6379` (Docker / WSL / Memurai) | `redis://redis:6379/0` (compose network) |
| `api` | `uvicorn app.main:app` (port 8002) | `api` container :8002 |
| `scheduler` | `python -m app.scheduler` | `scheduler` container |
| `worker` | `dramatiq app.workers` (http_checks + notifications) | `worker-http` container |
| `worker-browser` | `dramatiq app.workers --queues browser_checks` (`--threads 1`) | `worker-browser` container (Chromium in image) |
| `web` | `next dev` (frontend, port 3000) | `frontend` container (production build) :3000 |

Start natively with:

```powershell
powershell -File .\scripts\restart-stack.ps1
```

Or the whole stack in Docker:

```powershell
docker compose up -d --build
docker compose ps / logs -f api / down
```

Snapshots persist to the host `./data/snapshots` in both topologies
(`LOCAL_STORAGE_PATH=/data/snapshots` inside containers).

## Environments

| Env | Purpose |
| ----- | --------- |
| local | Dev |
| test | CI automated |

Staging/production are not configured (hosting config removed).

## Release basics

- Migrations via Alembic (`alembic upgrade head`)
- Health/readiness probes (`/health`, `/ready`)
- Worker concurrency via env

## Secrets

| Secret | Used by |
| -------- | --------- |
| `DATABASE_URL` | api, scheduler, workers |
| `REDIS_URL` | api, scheduler, workers |
| `CLERK_*` | api, web |
| `S3_*` / `R2_*` | workers, api (optional object storage) |
| `RESEND_API_KEY` | notification worker |
| `SECRET_KEY` | api (encryption key + API-key HMAC — pin in production) |
| `INTERNAL_API_TOKEN` | admin |

## Snapshot retention (matches `backend/app/services/retention.py`)

| Data | Default |
| ---- | ------- |
| Raw HTML + normalized-text objects | 30 days (`SNAPSHOT_RETENTION_DAYS`, purged with snapshot) |
| Snapshots (DB rows) | 30 days (same window) |
| Monitor runs | 90 days (`RUN_RETENTION_DAYS`) |
| Change events | Not purged by `retention_job` (only cascade when its snapshot is deleted) |
| Outbox / deliveries | Not purged by `retention_job` |

User delete monitor → delete associated history + enqueue object deletes.

## Production / hosting

- No deploy target or pipeline is configured (staging/production undecided — see roadmap Phase 10).
- The local Docker Compose topology (above) is for development; it is not a production deployment (single container, `APP_ENV` from `backend/.env`).
- Enterprise deploy is undecided — see roadmap Phase 10.
