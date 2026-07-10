# Deployment Plan

Status: **Approved for Phase 1 local + internal prototype**

## Local development

Docker Compose services:

| Service | Image / build |
|---------|----------------|
| `postgres` | postgres:16 |
| `redis` | redis:7 |
| `api` | backend FastAPI |
| `scheduler` | backend scheduler entrypoint |
| `worker` | Dramatiq workers (http + notifications) |
| `web` | Next.js (Phase 2; optional stub now) |
| `minio` (optional) | S3-compatible for R2 shim |

Developer workflow:

```text
docker compose up --build
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

## Internal prototype

Minimum:

- VM with **2–4 GB RAM** (e2-micro is **not** enough for full system + Playwright later)  
- Managed PostgreSQL when affordable  
- Redis with persistence appropriate to job durability strategy  
- Separate HTTP worker process  
- Cloudflare R2 for snapshots  
- Env-based secrets; no secrets in git  

## Public beta

- Managed PostgreSQL (automated backups + restore drills)  
- Managed Redis or well-operated Redis  
- Separately deployable: API, scheduler, HTTP workers, (later) browser workers  
- Staging + production  
- Resource and concurrency limits  
- Sentry + structured logs + queue depth metrics  
- Cloudflare (or similar) in front of API/web  

Kubernetes: **not** required until measured ops need.

## Environments

| Env | Purpose |
|-----|---------|
| local | Dev |
| test | CI automated |
| staging | Pre-prod |
| production | Users |

## Release basics

- Migrations via Alembic in deploy pipeline  
- Rollback procedure documented per release  
- Health/readiness probes  
- Worker concurrency via env  

## Secrets

| Secret | Used by |
|--------|---------|
| `DATABASE_URL` | api, scheduler, workers |
| `REDIS_URL` | api, scheduler, workers |
| `CLERK_*` | api, web (Phase 2) |
| `R2_*` / `S3_*` | workers, api |
| `RESEND_API_KEY` | notification worker |
| `SENTRY_DSN` | all apps |
| `INTERNAL_API_TOKEN` | Phase 1 admin |

## Snapshot retention (default proposal)

| Data | Default retention |
|------|-------------------|
| Raw HTML in R2 | 30 days |
| Normalized text in DB | 90 days or last N per monitor |
| Monitor runs | 90 days |
| Change events | 180 days |
| Outbox / deliveries | 30–90 days |

User delete monitor → delete associated history + enqueue object deletes.  
Document backup lag for “delete” semantics.
