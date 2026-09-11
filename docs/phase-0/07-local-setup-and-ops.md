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
| `SENTRY_DSN` | all apps |
| `INTERNAL_API_TOKEN` | admin |

## Snapshot retention (default proposal)

| Data | Default retention |
| ------ | ------------------- |
| Raw HTML | 30 days |
| Normalized text in DB | 90 days or last N per monitor |
| Monitor runs | 90 days |
| Change events | 180 days |
| Outbox / deliveries | 30–90 days |

User delete monitor → delete associated history + enqueue object deletes.
