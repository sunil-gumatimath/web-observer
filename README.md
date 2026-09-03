<p align="center">
  <img src="assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Web Observer

Web change-detection and alerting platform.

> Tell me when the web pages I care about change and clearly explain what changed.

## Status

**Phases 0–7 complete.** The original roadmap has been exceeded — the DB schema is at migration `012_add_ai_intelligence_fields` on Neon (post-roadmap work added storage optimization, the alerts inbox, monitor watch notes, brand/workspace-key columns, referential-integrity fixes, per-monitor conditional alert thresholds, natural-language semantic triggers, first-class AI impact/confidence triage, and distributed Redis dedup caching). Billing is optional (solo use: skip Stripe).

Verified end-to-end: backend unit tests pass, the frontend type-checks, and the FastAPI app exposes `api/v1` endpoints that match the frontend client.

| Doc | Topic |
|-----|--------|
| [docs/local-dev.md](docs/local-dev.md) | Run without Docker (full process list) |
| [docs/clerk-setup.md](docs/clerk-setup.md) | Clerk auth (dev) |
| [docs/clerk-production.md](docs/clerk-production.md) | Clerk production hardening |
| [docs/resend-setup.md](docs/resend-setup.md) | Email alerts |
| [docs/phase-3.md](docs/phase-3.md) | JS / Playwright / browser queue |
| [docs/phase-4.md](docs/phase-4.md) | Structured + visual modes |
| [docs/phase-5.md](docs/phase-5.md) | AI summaries, semantic triggers, Slack/Discord, digests |
| [docs/phase-6-7.md](docs/phase-6-7.md) | Plans, webhooks, API keys, RBAC |
| [docs/phase-0/](docs/phase-0/) | Discovery: scope, ERD, threat model, API outline |
| [docs/adrs/](docs/adrs/) | Architecture decision records |
| [docs/integrations/n8n-zapier.md](docs/integrations/n8n-zapier.md) | n8n / Zapier automation |
| [docs/architecture-uml.md](docs/architecture-uml.md) | Architecture diagrams |

## How monitoring works (short)

1. You create a monitor (URL + mode).  
2. Worker fetches the page (HTTP or Playwright) and builds a content hash.  
3. First success = **baseline** (no alert).  
4. Later hash differs → save diff → notify via configured channels (email / Slack / Discord) or outbound signed webhooks.

## Architecture

## Architecture

One idea: **you watch pages, workers do the checking, you get told only when something matters.**

```mermaid
flowchart LR
    YOU[You<br/>Next.js UI] --> API[API<br/>FastAPI]
    API --> DB[(Postgres<br/>monitors, snapshots,<br/>changes)]
    SCHED[Scheduler] --> DB
    SCHED --> Q[[Redis queue]]
    Q --> CHECK[Check workers<br/>fetch the page]
    CHECK --> PAGE((Web page))
    PAGE --> CHECK
    CHECK --> DB
    CHECK --> Q
    Q --> NOTIFY[Notify workers]
    NOTIFY --> ALERTS[Email · Slack<br/>Discord · Webhooks]
    ALERTS --> YOU
```

```mermaid
sequenceDiagram
    actor You
    participant UI as Next.js UI
    participant API as FastAPI
    participant DB as Postgres
    participant S as Scheduler
    participant Q as Redis queue
    participant W as Check worker
    participant P as Web page

    You->>UI: Create monitor (URL + mode)
    UI->>API: POST /monitors
    API->>DB: Save monitor
    S->>DB: Claim due monitors
    S->>Q: Enqueue check
    Q->>W: Run check
    W->>P: Fetch page
    P-->>W: HTML
    W->>DB: Compare hash + save snapshot
    alt First success
        W->>DB: Save baseline (no alert)
    else Content changed
        W->>DB: Save diff + AI summary
        W->>Q: Enqueue notify
        Q->>W: Send alert
        W-->>You: Email · Slack · Discord · Webhook
    end
```

**In plain English:**

1. **You create a monitor** (URL + what to watch) in the UI. The API saves it to Postgres.
2. **A scheduler wakes up every minute**, asks Postgres "which monitors are due?", and drops check jobs on a Redis queue. (Manual **Run now** skips the line and queues a job immediately.)
3. **Check workers fetch the page** — plain HTTP for normal pages, a real browser (Playwright) for JavaScript sites — and compare it to the last snapshot using a content hash.
   - First successful check → saved as the **baseline**, no alert.
   - Same content → nothing happens.
   - Changed → a diff is saved, an optional AI summary is attached, and noise (cookie banners, tiny edits below your thresholds) is marked but kept, not deleted.
4. **Notify workers send the alert** — email (Resend), Slack, Discord, or a signed webhook — and log the delivery. Quiet monitors are checked less often over time (adaptive scheduling).

<details>
<summary><strong>Under the hood (for contributors)</strong></summary>

- Workers are Python `dramatiq` (`backend/app/workers/checks.py:21`, `browser_checks.py:24`) on three queues — `http_checks`, `browser_checks`, `notifications` — via `RedisBroker` (`backend/app/workers/broker.py:9`).
- Due-monitor claiming is Postgres-driven (`SELECT ... FOR UPDATE SKIP LOCKED`, 60s lease + jitter: `backend/app/config.py:73-75`, `backend/app/scheduler.py:40`), so multiple schedulers never double-claim.
- Snapshots store raw HTML + normalized text with a SHA256 `content_hash`; change rows carry `is_noise` / `is_read`; webhooks are HMAC-signed (`X-MTW-Signature`).
- An external LLM is only called when `LLM_API_KEY` is set; otherwise summaries/triage use fast local heuristics.
- Full diagrams (components, ERD, sequence): `docs/architecture-uml.md`.

</details>

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
# Full stack (loads backend\.env, API :8002; processes launch with -WindowStyle Hidden, logs to data\logs)
powershell -File .\scripts\restart-stack.ps1
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
| Conditional alerting | Optional per-monitor `alert_config` JSONB (migration `011`) — thresholds evaluated in `backend/app/services/conditional.py:26` before notify: `price_below`/`price_above` + `percent_change` (`product_price`), `percent_change` (`json_field`, `page_content`), `list_min_added`/`list_min_removed` (`list_items`/`site_links`/`rss_feed`), `min_diff_chars`, `regex_must_match`/`regex_must_not_match`. Unmet thresholds mark the change `is_noise=true` with reason (stored, excluded from notifications/digests); empty config = alert on any hash difference. Set via `POST/PATCH /monitors` body or bulk import CSV/JSON `alert_config` column |
| Diffs | GitHub-style added/removed line views for every content change (unified diff + split view) via `GithubDiff` and readable markdown views |
| Screenshots | Opt-in per-monitor `screenshots_enabled`: capture happens only on non-noise (signal) changes (`backend/app/services/pipeline.py:743-756`), stored at `screenshots/{monitor_id}/{change.run_id}.png`; needs 2 signal changes for before/after comparison |
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
| Command palette | Ctrl+K / Cmd-K jump to pages + monitors |
| Toast notifications | Optimistic inbox feedback on read/noise/archive actions |
| Dashboard activity | 14-day Change-activity card on the dashboard |
| Threshold editor | `ThresholdEditor` alert_config form on New/Edit monitor (thresholds preview) |
| Monitor list | Search, mode-filter, status-tabs, and sorting on the monitors list |
| Onboarding checklist | First monitor → baseline → channel guided checklist |
| Channel test | Per-channel Send-test button in Settings → Alert channels |
| Visual comparison | Before/after drag slider on changes with screenshots (needs 2 signal changes) |

The web UI (Next.js) exposes: **Dashboard** (with 14-day Change-activity card), **Monitors** (list / new / edit / detail with search, mode-filter, status-tabs, sorting), **Changes** (per-change diff with before/after drag slider), **Alerts** (inbox with toast notifications), **Import** (bulk CSV/JSON), **Settings** (channels with per-channel Send-test, workspace, billing), and an in-app **Docs** page — plus a command palette (Ctrl+K/Cmd-K jump to pages + monitors) and an onboarding checklist (first monitor → baseline → channel).
## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q -m "not integration"
```

Quick smoke test of a running stack (API + worker must be up):

```sh
./scripts/smoke.sh
```


