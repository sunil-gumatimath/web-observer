# Local Setup & Ops Plan

Status: **Local development only.** The deployment/hosting configuration
(Cloud Run, Cloud Build, Render, Vercel, Docker, Compose, GCP) has been removed.
The app runs as local processes — see [docs/local-dev.md](../local-dev.md).

## Local development

| Service | How |
| ------- | --- |
| `postgres` | Neon URL or local Postgres (`DATABASE_URL`) |
| `redis` | local Redis on `localhost:6379` |
| `api` | `uvicorn app.main:app` (port 8002) |
| `scheduler` | `python -m app.scheduler` |
| `worker` | `dramatiq app.workers` (http_checks + notifications) |
| `worker-browser` | `dramatiq app.workers --queues browser_checks` (`--threads 1`) |
| `web` | `next dev` (frontend, port 3000) |

Start the full stack with:

```powershell
powershell -File .\scripts\restart-stack.ps1
```

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

- Hosting config was removed — the app runs as local processes only.
- Staging / production are not configured (no deploy target, no pipeline).
- Enterprise deploy is undecided — see roadmap Phase 10.
