<p align="center">
  <img src="assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Web Observer

Web change-detection and alerting platform.

> Tell me when the web pages I care about change and clearly explain what changed.

## Status

**Phases 0–7 complete.** The original roadmap has been exceeded — the DB schema is at migration `015_change_run_set_null` on Neon (post-roadmap work added storage optimization, the alerts inbox, monitor watch notes, brand/workspace-key columns, referential-integrity fixes, per-monitor conditional alert thresholds, natural-language semantic triggers, first-class AI impact/confidence triage, distributed Redis dedup caching, monitor tags, and encrypted webhook secrets at rest). Billing is optional (solo use: skip Stripe).

**Latest:** the whole stack (Redis, API, both Dramatiq workers, scheduler, frontend) runs as native processes with snapshots persisted to `./data/snapshots` and Neon staying external (Docker/Compose packaging removed); the monitor detail page is live via a rewritten SSE stream (1-hour lifetime with heartbeats and Redis-backed ORM wakeups so workers, the scheduler and the reaper surface status instantly); a shared run-logs service backs workspace-wide check history with an audited CSV/JSON export (`GET /workspaces/{id}/export/runs`, 20k-run cap); a full backend security review was applied (enforced per-principal rate limits that fail open to in-memory when Redis is down, atomic outbox/webhook claiming with attempt caps, a fenced stuck-run reaper, HKDF-purpose-separated crypto preserving legacy-token compatibility, and ReDoS/size caps on regex inputs); and the frontend was re-themed to the Cohere design system (white canvas, 22px signature cards, ghost buttons, `#1863dc` interaction blue, Space Grotesk/Inter, charcoal dark mode) with brand logos in the alerts inbox and an animated nav indicator.

**Cloudflare free tier (every piece optional, all $0):** raw snapshots live in R2; the Browser Rendering Worker is a **failover** for `js_required` fetches (local Playwright stays primary so the ~10 min/day edge-browser quota is preserved); a `security_scan` monitor mode is backed by the Cloudflare URL Scanner; screenshots can be served straight from a public R2 bucket over a custom domain; and a cookie-less Web Analytics beacon tracks the UI. Full setup: [docs/guides/cloudflare-free-features.md](docs/guides/cloudflare-free-features.md).

**Monitoring modes (9):** `page_content`, `site_links`, `product_price`, `list_items`, `json_field`, `rss_feed`, `readme`, `visual`, `security_scan`. Reference: [docs/guides/monitoring-modes.md](docs/guides/monitoring-modes.md).

Verified end-to-end (last run 2026-10-21): backend `283 passed, 4 skipped` unit tests (`11 deselected` integration tests run separately in CI), `ruff check` and `ruff format --check` clean; frontend `tsc` + ESLint clean (0 errors) and `89 passed` vitest tests across 13 files; `next build` compiles all routes; and the FastAPI app exposes `api/v1` endpoints that match the frontend client.

| Doc | Topic |
| ----- | -------- |
| [docs/](docs/) | Documentation index |
| [docs/local-dev.md](docs/local-dev.md) | Run locally (full process list) |
| [docs/guides/clerk-setup.md](docs/guides/clerk-setup.md) | Clerk auth (dev) |
| [docs/guides/clerk-production.md](docs/guides/clerk-production.md) | Clerk production hardening |
| [docs/auth-modes.md](docs/auth-modes.md) | Auth modes (dev token / Clerk) |
| [docs/guides/resend-setup.md](docs/guides/resend-setup.md) | Email alerts |
| [docs/guides/cloudflare-free-features.md](docs/guides/cloudflare-free-features.md) | Cloudflare free tier end-to-end (R2 snapshots, R2 screenshot CDN, Web Analytics, Tunnel, Browser Rendering failover, URL Scanner, Workers) |
| [docs/guides/web-analytics.md](docs/guides/web-analytics.md) | Cookie-less Cloudflare Web Analytics beacon |
| [docs/guides/monitoring-modes.md](docs/guides/monitoring-modes.md) | The 9 monitoring modes, their options and their limits |
| [docs/guides/r2-setup.md](docs/guides/r2-setup.md) | Cloudflare R2 snapshots (optional object storage) |
| [docs/phases/](docs/phases/) | Historical phase records (discovery → enterprise) |
| [docs/roadmap.md](docs/roadmap.md) | Feature roadmap (Phases 8–10) |
| [docs/adrs/](docs/adrs/) | Architecture decision records |
| [docs/integrations/n8n-zapier.md](docs/integrations/n8n-zapier.md) | n8n / Zapier automation |
| [docs/architecture.md](docs/architecture.md) | Architecture diagrams |

## How monitoring works (short)

1. You create a monitor (URL + mode).  
2. Worker fetches the page (HTTP or Playwright) and builds a content hash.  
3. First success = **baseline** (no alert).  
4. Later hash differs → save diff → notify via configured channels (email / Slack / Discord) or outbound signed webhooks.

## Architecture

One idea: **you watch pages, workers do the checking, you get told only when something matters.**

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

- Workers are Python `dramatiq` (`backend/app/workers/checks.py`, `browser_checks.py`) on three queues — `http_checks`, `browser_checks`, `notifications` — via `RedisBroker` (`backend/app/workers/broker.py`).
- Due-monitor claiming is Postgres-driven (`SELECT ... FOR UPDATE SKIP LOCKED`, 60s lease + jitter: `backend/app/config.py`, `backend/app/scheduler.py`), so multiple schedulers never double-claim.
- Snapshots store raw HTML + normalized text with a SHA256 `content_hash`; change rows carry `is_noise` / `is_read`; webhooks are HMAC-signed (`X-MTW-Signature`).
- An external LLM is only called when `LLM_API_KEY` is set; otherwise summaries/triage use fast local heuristics.
- The API also exposes Prometheus-compatible metrics at `GET /metrics` (rate limited to 30/min).
- Full diagrams (components, ERD, sequence): `docs/architecture.md`.

</details>

## What you need

| Piece | This project |
| -------- | ---------------- |
| Database | **Neon** Postgres (or local Postgres) — `DATABASE_URL` in `backend/.env` |
| Queue | **Redis** on `localhost:6379` |
| Auth | **Clerk** — keys in `frontend/.env.local` + JWKS in `backend/.env` |
| Email | **Resend** — optional for alerts |
| Snapshots | Local disk (`STORAGE_BACKEND=local`) or S3-compatible object storage |

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

Every supported variable is listed with its default in [`.env.example`](.env.example).

**`frontend/.env.local`:**

```env
# MUST match the API port you start (8000 or 8002)
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002
NEXT_PUBLIC_INTERNAL_API_TOKEN=dev-internal-token
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
# Optional: preselect a dev/seed workspace in the UI (internal-token mode only)
# NEXT_PUBLIC_DEV_WORKSPACE_ID=
# Optional Cloudflare Web Analytics beacon (empty = beacon never loads)
# NEXT_PUBLIC_CF_BEACON_TOKEN=
# Optional: serve screenshots from a public R2 bucket CDN instead of the API proxy
# NEXT_PUBLIC_SCREENSHOT_CDN_URL=https://screenshots.example.com
```

## Run locally

### One-time

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# required for JS rendering / screenshots:
python -m playwright install chromium
cd ..\frontend
npm ci # CI-canonical (also works: bun install)
```

### Every time (5 processes)

Redis must already be running. Prefer loading env from `backend/.env` (Neon).

| # | Process | Command |
| --- | --------- | --------- |
| 1 | **API** | `uvicorn app.main:app --host 127.0.0.1 --port 8002` |
| 2 | **HTTP worker** | `dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2` |
| 3 | **Browser worker** | `dramatiq app.workers --queues browser_checks --processes 1 --threads 1` |
| 4 | **Scheduler** | `python -m app.scheduler` |
| 5 | **Frontend** | `npm run dev` (port 3000) |

**Browser worker is required** for `js_required` monitors and opt-in `screenshots_enabled`.  
Use **`--threads 1`** on Windows. Playwright runs in a **subprocess** (`playwright_job`) to avoid `[Errno 9] Bad file descriptor`.

**Optional background jobs** (not required for manual checks or alerts):

| Job | Command | Purpose |
|-----|---------|---------|
| Digest | `python -m app.digest_job --loop` | Sends daily/weekly workspace digests (Phase 5) |
| Retention | `python -m app.retention_job` | Purges snapshots (default 30 days) and runs (default 90 days) |

These are separate processes. Run them on a schedule/cron.

**Helpers:**

```powershell
# Full stack (loads backend\.env, API :8002; processes launch with -WindowStyle Hidden, logs to data\logs)
powershell -File .\scripts\restart-stack.ps1
```

| URL | What |
| ----- | ------ |
| <http://127.0.0.1:3000> | UI |
| <http://127.0.0.1:8002/docs> | API docs |
| <http://127.0.0.1:8002/health> | API up? |
| <http://127.0.0.1:8002/ready> | DB reachable? |
| <http://127.0.0.1:8002/metrics> | Prometheus metrics |

If the UI shows **Failed to fetch**, the API is down or `NEXT_PUBLIC_API_BASE_URL` does not match the API port.

## First test flow

1. Open <http://127.0.0.1:3000> → **Sign up / Sign in** (Clerk).  
2. **Settings → Alert channels** → add your email (optional).  
3. **New monitor** → e.g. `https://example.com/` (enable screenshots for image history).  
4. Open monitor → **Run now** (first success = baseline, no alert).  

## Features

| Area | What's included |
| ------ | ----------------- |
| Monitoring modes | `page_content` (whole page text; `js_required` for SPAs), `readme` (GitHub repository README changes via `owner/repo` or full URL, renders GitHub-style markdown diffs), `site_links` (sitemap URL changes), `rss_feed` (RSS/Atom feed updates), `product_price` (price/currency, defaults to a daily schedule), `list_items` (CSS-selector link list), `json_field` (single value via JSONPath-style query, e.g. `$.data.price`, from a JSON endpoint), `visual` (perceptual screenshot comparison via a DCT pHash, `VISUAL_PHASH_THRESHOLD=8` bits of 256; the legacy aHash path keeps `VISUAL_AHASH_THRESHOLD=5`), `security_scan` (Cloudflare URL Scanner verdict + technology inventory, diffed item-by-item; needs `CLOUDFLARE_URLSCANNER_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`) — `site_links`/`rss_feed`/`readme`/`security_scan` fetch over plain HTTP only (`js_required` rejected at the schema layer); other modes can use the Playwright browser queue. Full reference: [docs/guides/monitoring-modes.md](docs/guides/monitoring-modes.md) |
| Visual element picker | Point-and-click selector picker on New/Edit monitor: proxied `POST /monitors/selector-preview` renders a sanitized preview, clicking an element synthesizes the most resilient CSS selector (`frontend/src/components/selector-picker.tsx`, `frontend/src/lib/selector.ts`); brand info auto-fill via `POST /monitors/brand-info` |
| Alert channels | Email (Resend), Slack webhook, Discord webhook |
| AI change summaries | Optional plain-language summaries per change (heuristic by default; enable any OpenAI-compatible gateway via `LLM_API_BASE`, default `api.kilo.ai` — and toggle per-workspace via `ai_summaries_enabled`) |
| LLM providers & model catalog | Two OpenAI-compatible providers: Kilo Gateway (free models, default `api.kilo.ai`) and Google Gemini (your own key, `GEMINI_API_KEY`). `LLM_API_BASE` picks the active one and the matching key is used automatically. `GET /api/v1/model-catalog` serves the selectable models per provider to the settings UI and drives the server-side failover (`backend/app/services/model_catalog.py`); every entry was verified live with the app's real prompt at the 200-token output cap |
| AI relevance filter | Optional per-monitor `watch_note` triage — LLM scores each diff vs. watch note; routine noise (cookie banners, ads, counters) is marked `is_noise=true`, held in dashboard (not deleted), excluded from notifications/digests, fails open on LLM error |
| Conditional alerting | Optional per-monitor `alert_config` JSONB (migration `011`) — thresholds evaluated in `backend/app/services/conditional.py:26` before notify: `price_below`/`price_above` + `percent_change` (`product_price`), `percent_change` (`json_field`, `page_content`), `list_min_added`/`list_min_removed` (`list_items`/`site_links`/`rss_feed`), `min_diff_chars`, `regex_must_match`/`regex_must_not_match`. Unmet thresholds mark the change `is_noise=true` with reason (stored, excluded from notifications/digests); empty config = alert on any hash difference. Set via `POST/PATCH /monitors` body or bulk import CSV/JSON `alert_config` column |
| Diffs | GitHub-style added/removed line views for every content change (unified diff + split view) via `GithubDiff` and readable markdown views |
| Change Q&A | Ask a question about any change from the change detail page (`POST /changes/{id}/ask-ai`, 5/minute) |
| Screenshots | Opt-in per-monitor `screenshots_enabled`: capture happens only on non-noise (signal) changes (`backend/app/services/pipeline.py:796-800`), stored at `screenshots/{monitor_id}/{change.run_id}.png`; needs 2 signal changes for before/after comparison. With `S3_SCREENSHOT_BUCKET` set, screenshots route to a dedicated public bucket and the frontend serves them from a CDN (`NEXT_PUBLIC_SCREENSHOT_CDN_URL`) instead of the API asset proxy |
| Outbound webhooks | Signed (`X-MTW-Signature`) deliveries on change events + delivery log with exponential backoff |
| API keys | `mtw_...` bearer tokens for programmatic access |
| Bulk workflows | CSV / JSON import + export of monitors and changes, plus sitemap URL discovery and batch creation |
| Workspace run logs | The **Logs** page lists every check run across the workspace with outcome (`all`/`success`/`failed`/`changed`), monitor and date filters (`GET /api/v1/workspaces/{id}/runs`; `backend/app/services/run_logs.py` powers both list and export so filters always match), refreshed on a 15s cadence |
| Check-history export | `GET /api/v1/workspaces/{id}/export/runs?format=csv\|json` honours the same filters as the logs list (20k-run cap), writes an `runs.exported` audit entry |
| Live monitor detail | SSE stream per monitor (`GET /api/v1/workspaces/{id}/monitors/{id}/events`): 1-hour lifetime with 15s heartbeats, Redis ORM-wakeup hints (`backend/app/services/live_events.py`) make worker/scheduler/reaper transitions instant and degrade to a 1.5s poll tick without Redis; the frontend adds reconnect backoff and stall detection + a `use-auto-refresh` hook fallback |
| Bulk pause / resume | Dashboard **Pause all** / **Resume all** (`POST /monitors/pause-all`, `POST /monitors/resume-all`) with confirm dialog and optimistic UI; resume re-schedules `next_run_at` promptly |
| Instant first check | Single-request `run_now` on monitor creation immediately queues an initial run and baseline check without extra round-trips |
| Alerts inbox | Every change stored in-app with `is_read`/`is_noise` state, independent of external notifications — filter Signal/Unread/Noise |
| Watch notes | Free-text `watch_note` per monitor drives AI relevance filter |
| Monitor tags | Optional list of up to 10 tags per monitor (migration `013`) — settable via `POST/PATCH /monitors` and the bulk-import `tags` column; no UI yet |
| Status badge | Public per-monitor SVG status badge (`GET /api/v1/workspaces/{id}/monitors/{id}/badge.svg`, no auth) for READMEs and dashboards |
| Digests | Daily / weekly workspace digest emails (background `digest_job`) — noise excluded |
| RBAC & audit | Owner / admin / member / viewer roles, member management, audit log |
| Plans / billing | free / pro / business / enterprise tiers; Stripe or simulated checkout (solo: skip Stripe) |
| Adaptive scheduling | Interval auto-stretches after quiet runs |
| Retention | Background `retention_job` purges snapshots (default 30 days) and runs (default 90 days); change events survive run cleanup (migration `015`) — `docs/operations/local-setup-and-ops.md` retention table is the source of truth |
| Brand-aware dashboard | Adding a website auto-fills logo/title/description/hero from page `<meta>` (`og:*`, favicon) and re-hosts via `brand-assets/` for dashboard + public share pages (no external Context.dev dependency). Alert inbox items carry `monitor_brand`; `BrandLogo` falls back to the domain favicon before initials, so a real mark shows even before enrichment runs |
| Design system | Cohere-inspired tokens (`frontend/src/app/globals.css`): 22px cards, pill buttons (dark solid primary, ghost secondary), `#1863dc` hover/focus blue, Space Grotesk display + Inter body, charcoal dark mode, sliding nav indicator + page fade on tab switch |
| Managed or self-serve keys | Server provides global `LLM_API_*`/`RESEND_API_KEY`; or each workspace brings its own keys in Settings → Workspace keys (overrides global) |
| Public share links | Opaque-token read-only public page per monitor (`/share/{token}` — unguessable, hashed at rest, expiring, no login required) |
| Teams | Expiring multi-use invite links (`/invite/{token}`) + switch between workspaces you belong to (`GET /me` + localStorage) |
| Command palette | Ctrl+K / Cmd-K jump to pages + monitors |
| Toast notifications | Optimistic inbox feedback on read/noise/archive actions |
| Dashboard activity | Change-activity card on the dashboard (7/14/30-day ranges, trend vs prior period, stacked bars by category). Backed by `GET /changes/activity?days=14&include_noise=false` (`days` 1–90, counts every event, noise excluded by default, capped at 20k rows, null category bucketed as `uncategorized`); UTC-safe client fallback buckets at most 1 per monitor when the endpoint is unreachable |
| Threshold editor | `ThresholdEditor` alert_config form on New/Edit monitor (thresholds preview) |
| Monitor list | Search, mode-filter, status-tabs, and sorting on the monitors list |
| Onboarding checklist | First monitor → baseline → channel guided checklist |
| Channel test | Per-channel Send-test button in Settings → Alert channels |
| Visual comparison | Before/after drag slider on changes with screenshots (needs 2 signal changes) |
| Fetch resilience | SSRF-pinned fetcher tries **every** validated IP in turn (`_pinned_get`), so one dead CDN PoP can't fail a check; only connect-level errors trigger failover. README monitors hit the GitHub API first (1 request, resolves the default branch) with capped raw fallbacks. LLM summaries fail over across `LLM_FALLBACK_MODELS` |
| Cloudflare Browser Rendering failover | When a local Playwright fetch fails, the check retries once against the edge Worker (`CLOUDFLARE_BROWSER_URL` + `CLOUDFLARE_BROWSER_TOKEN`). Local stays primary to preserve the free ~10 min/day browser quota. Worker source: `workers/browser-failover/`; covered by `backend/tests/test_browser_failover.py` |
| Observability | Prometheus-compatible metrics at `GET /metrics` (monitors total, runs/changes in 24h, outbox and webhook backlog) |
| Web Analytics | Optional cookie-less Cloudflare Web Analytics beacon on the UI (`NEXT_PUBLIC_CF_BEACON_TOKEN`); renders nothing when unset — see [docs/guides/web-analytics.md](docs/guides/web-analytics.md) |

The web UI (Next.js) exposes: **Dashboard** (with Change-activity card), **Monitors** (list / new / edit / detail with search, mode-filter, status-tabs, sorting), **Logs** (workspace-wide run history with outcome/monitor/date filters + CSV export), **Changes** (per-change diff with before/after drag slider), **Alerts** (inbox with toast notifications), **Import** (bulk CSV/JSON), **Settings** (channels with per-channel Send-test, workspace, billing), and an in-app **Docs** page — plus a command palette (Ctrl+K/Cmd-K jump to pages + monitors) and an onboarding checklist (first monitor → baseline → channel).

## Tests & Linting

```powershell
cd backend
.\.venv\Scripts\ruff check app tests
.\.venv\Scripts\ruff format --check app tests
.\.venv\Scripts\python -m pytest tests -q -m "not integration"

cd ..\frontend
npm run lint
npm test
npm run build
```

CI (`.github/workflows/ci.yml`) runs the backend unit tests and the Postgres-backed integration tests in separate jobs, plus a Gitleaks secret scan, and the frontend type-check / lint / test / build.

Quick smoke test of a running stack (API + worker must be up):

```sh
./scripts/smoke.sh
```
