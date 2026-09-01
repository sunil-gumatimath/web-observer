<p align="center">
  <img src="frontend/public/logo.svg" alt="Web Observer logo" width="260" />
</p>

# Web Observer

Web change-detection and alerting platform.

> Tell me when the web pages I care about change and clearly explain what changed.

## Status

**Phases 0–7 complete.** The original roadmap has been exceeded — the DB schema is at migration `010_add_missing_foreign_keys` (post-roadmap work added a storage optimization, the alerts inbox, monitor watch notes, brand/workspace-key columns, and referential-integrity fixes). Billing is optional (solo use: skip Stripe).

Verified end-to-end: backend unit tests pass, the frontend type-checks, and the FastAPI app exposes `api/v1` endpoints that match the frontend client.

| Doc | Topic |
|-----|--------|
| [docs/local-dev.md](docs/local-dev.md) | Run without Docker (full process list) |
| [docs/clerk-setup.md](docs/clerk-setup.md) | Clerk auth (dev) |
| [docs/clerk-production.md](docs/clerk-production.md) | Clerk production hardening |
| [docs/resend-setup.md](docs/resend-setup.md) | Email alerts |
| [docs/phase-3.md](docs/phase-3.md) | JS / Playwright / browser queue |
| [docs/phase-4.md](docs/phase-4.md) | Structured + visual modes |
| [docs/phase-5.md](docs/phase-5.md) | AI summaries, Slack/Discord, digests |
| [docs/phase-6-7.md](docs/phase-6-7.md) | Plans, webhooks, API keys, RBAC |
| [docs/phase-0/](docs/phase-0/) | Discovery: scope, ERD, threat model, API outline |
| [docs/adrs/](docs/adrs/) | Architecture decision records |
| [docs/integrations/n8n-zapier.md](docs/integrations/n8n-zapier.md) | n8n / Zapier automation |
| [docs/architecture-uml.md](docs/architecture-uml.md) | Architecture diagrams |
| `web-observer-final-roadmap.md` | Original product roadmap (historical) |

## How monitoring works (short)

1. You create a monitor (URL + mode).  
2. Worker fetches the page (HTTP or Playwright) and builds a content hash.  
3. First success = **baseline** (no alert).  
4. Later hash differs → save diff → notify via configured channels (email / Slack / Discord) or outbound signed webhooks.

## Architecture

```mermaid
sequenceDiagram
    autonumber
    participant S as Scheduler
    participant API as FastAPI
    participant DB as Postgres
    participant R as Redis (broker)
    participant W as Check Worker (dramatiq)
    participant T as Monitored page
    participant P as Pipeline
    participant OBJ as Object Storage
    participant N as Notify/Webhook Worker
    participant EXT as Email · Slack · Discord · Webhook

    Note over API: Manual run: POST /monitors/{id}/run also enqueues a check

    S->>DB: claim_due_monitors (FOR UPDATE SKIP LOCKED)
    DB-->>S: due monitors (60s lease + jitter)
    S->>R: enqueue_check(run_id, needs_browser)
    R->>W: run_http_check / run_browser_check
    W->>T: fetch_url / Playwright (+ optional screenshot)
    T-->>W: FetchResult (text, status, latency)
    W->>P: apply_fetch_result(monitor, run, result)
    P->>OBJ: store raw html + normalized text
    P->>DB: insert Snapshot (SHA256 content_hash)

    alt first success
        P-->>W: baseline set — no alert
    else same hash / similar image
        P-->>W: unchanged — no alert
    else content changed
        P->>P: unified diff → AI summary + watch_note triage
        P->>DB: insert ChangeEvent (is_noise, is_read)
        P->>DB: insert NotificationOutbox + WebhookDelivery
        W->>R: enqueue deliver_outbox_message / deliver_webhook_message
        N->>EXT: send email (Resend) / Slack / Discord / signed webhook (X-MTW-Signature)
        EXT-->>N: delivery logged
    end

    W->>DB: run status = succeeded/failed (adaptive interval update)
```

* **No `worker.ts` / `SCRAPE_CRON` / `Context.dev API`.** Workers are Python `dramatiq` (`backend/app/workers/checks.py:21`, `browser_checks.py:24`) via `RedisBroker` (`backend/app/workers/broker.py:9`). Scheduling is Postgres-driven `claim_due_monitors` (`SELECT ... FOR UPDATE SKIP LOCKED`) with 60s lease + jitter `backend/app/config.py:73-75`, `backend/app/scheduler.py:40`. Extraction/screenshot is in-process (`backend/app/services/pipeline.py:56`, `backend/app/services/visual.py:280`) only calling an external LLM when `LLM_API_KEY` is set (OpenAI or `https://ai-gateway.vercel.sh/v1`). Snapshots cover all 4 modes, not just sitemap/markdown/product.
* Full diagrams: `docs/architecture-uml.md` (Components, ERD, Sequence).  

## What you need

| Piece | This project |
|--------|----------------|
| Database | **Neon** Postgres (or local Postgres) — `DATABASE_URL` in `backend/.env` |
| Queue | **Redis** on `localhost:6379` |
| Auth | **Clerk** — keys in `frontend/.env.local` + JWKS in `backend/.env` |
| Email | **Resend** — optional for alerts |
| Snapshots | Local disk (`STORAGE_BACKEND=local`) — no MinIO |
| Docker | **Not required** |

## Env files (do not commit secrets)

**`backend/.env`:**

```env
# development | test | production
# Not optional: development mode is opt-in. An unset APP_ENV is treated as a
# non-development environment so the production guards stay active.
APP_ENV=development

DATABASE_URL=postgresql+psycopg://USER:PASS@HOST/neondb?sslmode=require
REDIS_URL=redis://localhost:6379/0
STORAGE_BACKEND=local
INTERNAL_API_TOKEN=dev-internal-token

# Derives both the encryption key for workspace BYO secrets and the API-key
# HMAC. Pin a stable value in production — restart with a random value makes
# stored workspace keys unreadable and invalidates every mtw_ API key.
SECRET_KEY=change-me-in-production

CLERK_JWKS_URL=https://YOUR-INSTANCE.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://YOUR-INSTANCE.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...
```

Use `postgresql+psycopg://` (not plain `postgresql://`).

**Production:** set `APP_ENV=production` and pin `SECRET_KEY` / `INTERNAL_API_TOKEN`
to real values. Outside development the API refuses to start if either is
missing or still holds a placeholder — and `Base.metadata.create_all()` is
skipped, so schema changes come only from Alembic.

Apply schema changes with Alembic (the single source of truth):

```powershell
cd backend
alembic upgrade head
```

**`frontend/.env.local`:**

```env
# MUST match the API port you start (8000 or 8002)
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002
NEXT_PUBLIC_INTERNAL_API_TOKEN=dev-internal-token
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
# Optional: preselect a dev/seed workspace in the UI (internal-token mode only)
# NEXT_PUBLIC_DEV_WORKSPACE_ID=
```

## Run locally (no Docker)

### One-time

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# required for Visual / JS monitors:
python -m playwright install chromium

cd ..\frontend
bun install # or npm install
```

### Every time (5 processes)

Redis must already be running. Prefer loading env from `backend/.env` (Neon).

| # | Process | Command |
|---|---------|---------|
| 1 | **API** | `uvicorn app.main:app --host 127.0.0.1 --port 8002` |
| 2 | **HTTP worker** | `dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2` |
| 3 | **Browser worker** | `dramatiq app.workers --queues browser_checks --processes 1 --threads 1` |
| 4 | **Scheduler** | `python -m app.scheduler` |
| 5 | **Frontend** | `bun run dev` or `npm run dev` (port 3000) |

**Browser worker is required** for `js_required` monitors and opt-in `screenshots_enabled`.  
Use **`--threads 1`** on Windows. Playwright runs in a **subprocess** (`playwright_job`) to avoid `[Errno 9] Bad file descriptor`.

**Optional background jobs** (not required for manual checks or alerts):

| Job | Command | Purpose |
|-----|---------|---------|
| Digest | `python -m app.digest_job --loop` | Sends daily/weekly workspace digests (Phase 5) |
| Retention | `python -m app.retention_job` | Purges runs/snapshots older than `RUN_RETENTION_DAYS` (default 90) |

These are separate processes (the Docker Compose `digest` service runs the loop automatically). Run them on a schedule/cron in production.

**Helpers:**

```powershell
# Full stack (loads backend\.env, API :8002, opens WO-* windows)
powershell -File .\scripts\restart-stack.ps1

# Older helper (hardcodes local Postgres + port 8000 — prefer restart-stack or manual)
.\scripts\run-local.ps1
```

| URL | What |
|-----|------|
| http://127.0.0.1:3000 | UI |
| http://127.0.0.1:8002/docs | API docs |
| http://127.0.0.1:8002/health | API up? |
| http://127.0.0.1:8002/ready | DB reachable? |

If the UI shows **Failed to fetch**, the API is down or `NEXT_PUBLIC_API_BASE_URL` does not match the API port.

## First test flow

1. Open http://127.0.0.1:3000 → **Sign up / Sign in** (Clerk).  
2. **Settings → Alert channels** → add your email (optional).  
3. **New monitor** → e.g. `https://example.com/` (enable screenshots for image history).  
4. Open monitor → **Run now** (first success = baseline, no alert).  

## Features

| Area | What's included |
|------|-----------------|
| Monitoring modes | `page_content` (whole page text; `js_required` for SPAs), `readme` (GitHub repository README changes via `owner/repo` or full URL, renders GitHub-style markdown diffs), `site_links` (sitemap URL changes), `rss_feed` (RSS/Atom feed updates), `product_price` (price/currency, defaults to a daily schedule), `list_items` (CSS-selector link list), `json_field` (single value via JSONPath-style query, e.g. `$.data.price`, from a JSON endpoint) — list modes (`site_links`/`list_items`) fetch over plain HTTP only |
| Alert channels | Email (Resend), Slack webhook, Discord webhook |
| AI change summaries | Optional plain-language summaries per change (heuristic by default; enable OpenAI-compatible LLM via `LLM_API_BASE` — works with OpenAI or Vercel AI Gateway — and toggle per-workspace via `ai_summaries_enabled`) |
| AI relevance filter | Optional per-monitor `watch_note` triage — LLM scores each diff vs. watch note; routine noise (cookie banners, ads, counters) is marked `is_noise=true`, held in dashboard (not deleted), excluded from notifications/digests, fails open on LLM error |
| Diffs | GitHub-style added/removed line views for every content change (unified diff + split view) via `GithubDiff` and readable markdown views |
| Screenshots | Opt-in per-monitor `screenshots_enabled`: when enabled, every check captures a fresh Playwright screenshot (`brand-assets/` + `screenshots/` storage) with aHash history and side-by-side comparison |
| Outbound webhooks | Signed (`X-MTW-Signature`) deliveries on change events + delivery log with exponential backoff |
| API keys | `mtw_...` bearer tokens for programmatic access |
| Bulk workflows | CSV / JSON import + export of monitors and changes, plus sitemap URL discovery and batch creation |
| Instant first check | Single-request `run_now` on monitor creation immediately queues an initial run and baseline check without extra round-trips |
| Alerts inbox | Every change stored in-app with `is_read`/`is_noise` state, independent of external notifications — filter Signal/Unread/Noise |
| Watch notes | Free-text `watch_note` per monitor drives AI relevance filter |
| Digests | Daily / weekly workspace digest emails (background `digest_job`) — noise excluded |
| RBAC & audit | Owner / admin / member / viewer roles, member management, audit log |
| Plans / billing | free / pro / business / enterprise tiers; Stripe or simulated checkout (solo: skip Stripe) |
| Adaptive scheduling | Interval auto-stretches after quiet runs |
| Retention | Background `retention_job` purges old runs / snapshots (default 90 days) |
| Brand-aware dashboard | Adding a website auto-fills logo/title/description/hero from page `<meta>` (`og:*`, favicon) and re-hosts via `brand-assets/` for dashboard + public share pages (no external Context.dev dependency) |
| Managed or self-serve keys | Server provides global `LLM_API_*`/`RESEND_API_KEY`; or each workspace brings its own keys in Settings → Workspace keys (overrides global) |
| Public share links | Opaque-token read-only public page per monitor (`/share/{token}` — unguessable, hashed at rest, expiring, no login required) |
| Teams | Expiring multi-use invite links (`/invite/{token}`) + switch between workspaces you belong to (`GET /me` + localStorage) |
| Opt-in screenshots | `screenshots_enabled` (off by default) — when enabled, every check captures a fresh screenshot at a glance |

The web UI (Next.js) exposes: **Dashboard**, **Monitors** (list / new / edit / detail), **Changes** (per-change diff), **Alerts** (inbox), **Import** (bulk CSV/JSON), **Settings** (channels, workspace, billing), and an in-app **Docs** page.
## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q -m "not integration"
```

Quick smoke test of a running stack (API + worker must be up):

```powershell
# Windows
.\scripts\smoke.ps1
# Linux / macOS
./scripts/smoke.sh
```

## Stack

Python / FastAPI · Neon Postgres · Redis / Dramatiq · Next.js · Clerk · Resend · local disk snapshots · Playwright

### webdog.ai-parity additions (post-roadmap)

These extend the platform beyond the original roadmap:

- **Brand-aware dashboard** — adding a website auto-fills title/description/logo/hero from HTML `<meta>` (no Context.dev) and re-hosts via `brand-assets/` for dashboard + public share pages. Also refreshable via per-monitor *Brand* action (`POST /workspaces/{id}/monitors/{id}/brand`).
- **GitHub README & RSS monitoring** — dedicated `readme` mode for tracking repository documentation updates with GitHub Markdown styling and `rss_feed` mode for syndication feeds.
- **Single-roundtrip monitor creation** — `run_now` flag batches monitor creation and initial check queuing into a single transaction and HTTP request.
- **Managed or self-serve keys** — a workspace owner can set per-workspace LLM keys (`llm_api_key` / `llm_api_base` / `llm_model`) and Resend keys (`resend_api_key` / `email_from`) in **Settings → Workspace keys**. AI summaries and email alerts use the workspace keys when present, otherwise the global keys. Works with OpenAI or Vercel AI Gateway (set `LLM_API_BASE=https://ai-gateway.vercel.sh/v1`). Settings values are masked on read.
- **Public share links** — from a monitor's detail page, *Share* creates an opaque-token link (`/share/{token}`) that anyone can open to view the monitor's change history. The token is hashed at rest (only its prefix is stored) and the link is revocable.
- **Teams** — **Settings → Team** generates expiring multi-use invite links with role/max-uses. Switch workspaces via `GET /me` and `localStorage` (`web_observer_workspace_id`).
- **Opt-in screenshots** — `screenshots_enabled` off by default; when enabled, every check captures a fresh Playwright screenshot (`screenshots/{monitor_id}/{run_id}.png`) with aHash history.

> Database: apply schema changes with `alembic upgrade head` from `backend/`.
> removed so there is only one schema-application path. In development the API
> also runs `Base.metadata.create_all()` at startup; in production it does not,
> so migrations are never silently bypassed.
