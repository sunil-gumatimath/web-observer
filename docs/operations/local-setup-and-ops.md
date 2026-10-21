# Local Setup & Ops Plan

Status: **Local development** via native processes (the 5-process launcher
`scripts/restart-stack.ps1` or manual processes — see [docs/local-dev.md](../local-dev.md)).

Cloud deployment/hosting configuration (Cloud Run, Cloud Build, Render, Vercel) has not
been configured — see the last section.

## Local development

| Service | Native |
| --------- | --------------------------------------- |
| `postgres` | Neon URL or local Postgres (`DATABASE_URL`) |
| `redis` | `localhost:6379` (WSL / Memurai) |
| `api` | `uvicorn app.main:app` (port 8002) |
| `scheduler` | `python -m app.scheduler` |
| `worker` | `dramatiq app.workers` (http_checks + notifications) |
| `worker-browser` | `dramatiq app.workers --queues browser_checks` (`--threads 1`) |
| `web` | `next dev` (frontend, port 3000) |

Start with:

```powershell
powershell -File .\scripts\restart-stack.ps1
```

Snapshots persist to `./data/snapshots`.

## Environments

| Env | Purpose |
| ----- | --------- |
| local | Dev |
| test | CI automated |

Staging/production are not configured (hosting config removed).

## Release basics

- Migrations via Alembic (`alembic upgrade head`) — the schema's only source of truth
  (head revision: `015_change_run_set_null`)
- Health/readiness probes (`/health`, `/ready`)
- Prometheus metrics (`/metrics`, rate limited to 30/minute): monitors total,
  runs and changes in the last 24h, outbox and webhook backlog
- Worker concurrency via env

## Cloudflare Workers

Two Workers live in `workers/` and are deployed separately from the app:

| Worker | Purpose | Source |
| ------ | ------- | ------ |
| `browser-failover` | Edge Chromium used **only** as a failover for `js_required` fetches, after a local Playwright fetch has already failed. Free quota is ~10 min of browser time per UTC day, so local stays primary. | `workers/browser-failover/` |
| `share-cache` | Edge cache for public share pages and Next.js static assets (`/share/`, `/_next/static/`). Deployed standalone; attach routes when a public hostname exists. | `workers/share-cache/` |

Neither Worker is required for the stack to run. If `CLOUDFLARE_BROWSER_URL` is
unset, the failover is simply off and a failed browser check fails.

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
| `LLM_API_KEY` / `GEMINI_API_KEY` | api + workers (AI summaries, triage) |
| `CLOUDFLARE_BROWSER_TOKEN` | workers (Browser Rendering failover) |
| `CLOUDFLARE_URLSCANNER_TOKEN` | workers (`security_scan` mode) |

## Snapshot retention (matches `backend/app/services/retention.py`)

| Data | Default |
| ---- | ------- |
| Raw HTML + normalized-text objects | 30 days (`SNAPSHOT_RETENTION_DAYS`, purged with the snapshot) |
| Screenshot objects | 30 days (same window, deleted with the snapshot that produced them) |
| Snapshots (DB rows) | 30 days (same window) — **but** a snapshot still referenced by a change event is kept |
| Monitor runs | 90 days (`RUN_RETENTION_DAYS`) |
| Change events | **Never purged** by `retention_job`. Since migration `015` a change event's `run_id` is `SET NULL`, so run cleanup no longer destroys the alerts inbox, and a snapshot referenced as a change's `new_snapshot` is explicitly retained. |
| Outbox / deliveries | Not purged by `retention_job` |

User delete monitor → delete associated history + enqueue object deletes.

> Retention is deliberately biased towards keeping the inbox: a change event
> without its snapshot is still a usable record (title, impact, summary, diff
> summary), while losing a change event loses user-visible history.
> See `backend/app/services/retention.py` and
> `backend/tests/test_retention_events.py`.

## Production / hosting

- No deploy target or pipeline is configured (staging/production undecided — see roadmap Phase 10).
- Enterprise deploy is undecided — see roadmap Phase 10.
