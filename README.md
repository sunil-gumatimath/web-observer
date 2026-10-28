<p align="center">
  <img src="assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Web Observer

Web change-detection and alerting platform.

> Tell me when the web pages I care about change and clearly explain what changed.

- **9 monitoring modes** — page text, sitemaps, RSS/Atom, GitHub READMEs, prices, CSS-selector lists, JSON values, visual screenshots, and Cloudflare security scans.
- **Intelligence, not spam** — content-hashing diffs, conditional thresholds, watch-note AI triage, and noise marking mean you only get told when something matters.
- **Reliable delivery** — email (Resend), Slack, Discord, HMAC-signed webhooks, and an in-app alerts inbox, all driven by an outbox with bounded retries.
- **Runs anywhere** — local processes (Windows/Linux) against a hosted Neon Postgres + local Redis, with optional `$0` Cloudflare edge workers for failover fetching, scan verdicts and share-page caching.
- **Built for teams** — workspaces, RBAC, audit log, API keys, invited links, public share pages, and per-workspace BYO keys.

## Status

**Phases 0–7 complete** — the original roadmap has been exceeded. Post-roadmap work added the alerts inbox, per-monitor conditional thresholds and semantic triggers, first-class AI impact/confidence triage, distributed Redis dedup caching, monitor tags, workspace run logs with CSV/JSON export, brand/enrichment columns, encrypted webhook secrets, and per-principal rate limits. DB schema is at Alembic migration `015_change_run_set_null`. Billing is optional (solo use: skip Stripe).

Cloudflare free tier is wired end-to-end and every piece is optional: raw snapshots in R2, a Browser Rendering **failover** Worker for `js_required` fetches (local Playwright stays primary so the ~10 min/day edge-browser quota is preserved), a `security_scan` monitor mode backed by the URL Scanner, screenshots served from a public R2 bucket over a custom domain, and a cookie-less Web Analytics beacon. Full setup: [docs/guides/cloudflare-free-features.md](docs/guides/cloudflare-free-features.md).

Verified end-to-end (last run 2026-10-26): backend `335 passed` unit tests (integration tests run separately in CI), `ruff check` and `ruff format --check` clean; frontend `tsc` + ESLint clean (0 errors) and `94 passed` vitest tests across 13 files; `next build` compiles all routes; the FastAPI app exposes `api/v1` endpoints that match the frontend client.

## Documentation

| Doc | Topic |
| ----- | -------- |
| [docs/](docs/) | Documentation index |
| [docs/local-dev.md](docs/local-dev.md) | Run locally + operations reference (processes, secrets, retention) |
| [docs/architecture.md](docs/architecture.md) | Deep architecture: module/package diagram, full ERD, manual-run + pipeline-decision sequences, service notes |
| [docs/auth-modes.md](docs/auth-modes.md) | Auth modes (dev token / Clerk) |
| [docs/guides/clerk.md](docs/guides/clerk.md) | Clerk auth (dev setup + production hardening) |
| [docs/guides/resend-setup.md](docs/guides/resend-setup.md) | Email alerts |
| [docs/guides/cloudflare-free-features.md](docs/guides/cloudflare-free-features.md) | Cloudflare free tier end-to-end (R2 snapshots, R2 screenshot CDN, Web Analytics, Tunnel, Browser Rendering failover, URL Scanner, Workers) |
| [docs/guides/monitoring-modes.md](docs/guides/monitoring-modes.md) | The 9 monitoring modes, their options and limits |
| [docs/roadmap.md](docs/roadmap.md) | Feature roadmap (Phases 8–10) |
| [docs/security/threat-model.md](docs/security/threat-model.md) | Security policy: SSRF, tenant isolation, out-of-scope rules |
| [docs/adrs/](docs/adrs/) | Architecture decision records |
| [docs/integrations/n8n-zapier.md](docs/integrations/n8n-zapier.md) | n8n / Zapier automation |

## How it works (short)

1. You create a monitor (URL + mode).
2. Workers fetch the page (HTTP or Playwright in a real browser) and build a content hash.
3. First success = **baseline** (no alert).
4. A later hash differs → save the diff → notify via email / Slack / Discord, or an outbound signed webhook.

## Architecture

The whole system is one idea: **you watch pages, workers do the checking, and you get told only when something matters.**

Stack: **Next.js** (App Router, React 19, Clerk, Tailwind) → **FastAPI** → **Neon Postgres** + **Redis** (Dramatiq broker) → **Dramatiq workers** (HTTP / Playwright / notifications) → alert channels. Snapshots persist to local disk (`./data/snapshots`) or S3-compatible object storage; Alembic owns the schema.

### Component map

```mermaid
flowchart TB
    subgraph Browser["Browser"]
        UI["Next.js UI · :3000<br/>Clerk auth · live SSE · visual diff viewer"]
    end

    subgraph Procs["Local processes"]
        API["FastAPI · :8002<br/>REST /api/v1 · SSE streams · /metrics"]
        SCHED["Scheduler<br/>claims due monitors<br/>60s lease + stuck-run reaper"]
        WHTTP["HTTP check worker<br/>http_checks queue"]
        WBROWSER["Browser check worker<br/>Playwright subprocess<br/>browser_checks queue"]
        WNOTIFY["Notification workers<br/>notifications queue"]
        JOBS["Digest + Retention jobs<br/>standalone loops (optional)"]
    end

    subgraph Stores["Data stores"]
        PG[("Neon Postgres<br/>monitors · runs · snapshots · changes")]
        RD[("Redis<br/>queues · rate limits · SSE wakeup hints")]
        ST[("Snapshots<br/>./data/snapshots or S3/R2")]
    end

    subgraph Edge["Cloudflare edge — optional, free tier"]
        BF["browser-failover worker<br/>edge Chromium, retry path only"]
        SCS["share-cache worker<br/>caches /share/ pages"]
        SCAN["URL Scanner<br/>security_scan verdicts"]
    end

    TARGET["Monitored web pages"]
    CHANNELS["Resend · Slack · Discord"]
    CLERK["Clerk (JWTs + JWKS)"]

    UI -->|"REST + SSE"| API
    API <--> CLERK
    API <--> PG
    API -->|"manual run / import"| RD
    SCHED <--> PG
    SCHED -->|"enqueue checks"| RD
    RD --> WHTTP
    RD --> WBROWSER
    RD --> WNOTIFY
    WHTTP <--> PG
    WBROWSER <--> PG
    WNOTIFY <--> PG
    WHTTP --> ST
    WBROWSER --> ST
    WHTTP --> TARGET
    WBROWSER --> TARGET
    WBROWSER -->|"local Playwright fetch failed"| BF
    BF --> TARGET
    WBROWSER -->|"security_scan mode"| SCAN
    WNOTIFY --> CHANNELS
    JOBS <--> PG
    JOBS --> CHANNELS
    UI -.->|"/share/ pages"| SCS
```

### A check from start to finish

```mermaid
sequenceDiagram
    actor You
    participant UI as Next.js UI
    participant API as FastAPI
    participant DB as Neon Postgres
    participant S as Scheduler
    participant Q as Redis queue
    participant W as Check workers
    participant P as Target page
    participant N as Notify channels

    You->>UI: Create monitor (URL + mode)
    UI->>API: POST /monitors
    API->>DB: Save monitor + queue immediate first check
    loop Every minute
        S->>DB: Claim due monitors (FOR UPDATE SKIP LOCKED, 60s lease)
        S->>Q: Enqueue check jobs
    end
    Q->>W: Run check (HTTP or Playwright)
    W->>P: Fetch page
    P-->>W: Content
    W->>DB: Hash + snapshot + compare to previous run
    alt First success
        W->>DB: Save baseline (no alert)
    else Unchanged (hash or visual pHash)
        W-->>UI: Quiet — adaptive interval may stretch
    else Changed
        W->>DB: Save diff + AI summary (thresholds + noise triage applied)
        W->>Q: Enqueue notifications
        Q->>W: Deliver
        W-->>N: Email · Slack · Discord · signed webhook
    end
    W-->>UI: SSE live update on the monitor detail page
```

### What happens on a change

```mermaid
flowchart LR
    A["Fetch"] --> B{"HTTP error or<br/>empty extraction?"}
    B -->|yes| FAIL["Run failed<br/>logged; failure alert after N"]
    B -->|no| C["Hash content"]
    C --> D{"First success?"}
    D -->|yes| BASE["Baseline — no alert"]
    D -->|no| E{"Hash / visual pHash<br/>same as previous?"}
    E -->|yes| SAME["Unchanged — no alert"]
    E -->|no| F{"Conditional thresholds +<br/>watch-note AI triage"}
    F -->|"noise or below threshold"| NOISE["Held in Alerts inbox<br/>is_noise=true · no notify"]
    F -->|signal| CHANGE["Change event<br/>diff + AI summary<br/>+ screenshot if enabled"]
    CHANGE --> G["Notify channels ·<br/>signed webhooks · inbox"]
```

<details>
<summary><strong>Under the hood (for contributors)</strong></summary>

- Workers are Python `dramatiq` (`backend/app/workers/checks.py`, `browser_checks.py`) on three queues — `http_checks`, `browser_checks`, `notifications` — via `RedisBroker` (`backend/app/workers/broker.py`). Alerts fan out from `NotificationOutbox` / `WebhookDelivery` rows, so detection is decoupled from delivery with at-least-once sends (`max_retries=5`).
- Due-monitor claiming is Postgres-driven (`SELECT ... FOR UPDATE SKIP LOCKED`, 60s lease + jitter: `backend/app/config.py`, `backend/app/scheduler.py`), so multiple schedulers never double-claim. `run_reaper` recovers stuck runs with a fenced conditional update, and the worker-side terminal writes are fenced too: the pipeline's SUCCEEDED commit and `fail_run` are both conditional `UPDATE ... WHERE status = 'running'`, so a reaper (or a late exception) can never overwrite a run's committed terminal state — no zombie SUCCEEDED-over-FAILED (or FAILED-over-SUCCEEDED) downgrade race.
- Snapshots store raw HTML + normalized text with a SHA256 `content_hash`; visual mode compares SHA512-based pHash (256 bits, threshold 8). Change rows carry `is_noise` / `is_read`; webhooks are HMAC-signed (`X-MTW-Signature`) with secrets encrypted at rest.
- Rate limiting is enforced per verified principal (or IP) via Redis counters; when Redis is down the limiter fails open to in-memory counters, so an outage can't turn unrelated requests into 500s.
- An external LLM is only called when `LLM_API_KEY` is set; otherwise summaries/triage use fast local heuristics. Optional SubQ Decisions API (`SUBQ_ENABLED`) acts as a fast System 1 triage gate for probabilistic noise rejection and category/impact scoring before generative LLM summarization. `GET /api/v1/model-catalog` serves selectable models per provider.
- Browser runs automatically queue advisory hero preview screenshot captures (`screenshots/{monitor_id}/{run_id}.png`) via Dramatiq off the critical path, populating monitor card headers without manual intervention.
- The API also exposes Prometheus-compatible metrics at `GET /metrics` (rate limited to 30/min).
- SSRF guard (`backend/app/security/ssrf.py`): private/loopback/link-local/metadata IPs and credentialed URLs are blocked before fetch; redirects are re-validated; the pinned fetcher tries every validated IP in turn so a dead CDN PoP can't fail a check. SSRF exceptions convert gracefully to fetch errors, ensuring external provider DNS hiccups (e.g. during brand asset extraction) never trigger unhandled 500s.
- Full diagrams (components, ERD, manual-run + decision sequences): [docs/architecture.md](docs/architecture.md).

</details>

### Project layout

```text
├── backend/             # FastAPI app + Dramatiq workers + Alembic migrations (head: 015)
│   ├── app/             #   routers · services · workers · models · security
│   ├── alembic/         #   schema migrations — single source of truth
│   └── tests/           #   unit + Postgres-backed integration tests
├── frontend/            # Next.js (App Router) · React 19 · Clerk · Tailwind · vitest
├── workers/             # Cloudflare Workers: browser-failover, share-cache
├── docs/                # guides · architecture · ADRs · threat model
├── scripts/             # restart/stop stack helpers (Windows + Linux/WSL)
├── assets/              # brand SVGs (source of truth for logo/favicon/OG image)
└── data/                # runtime artifacts: snapshots + logs (local only)
```

## What you need

| Piece | This project |
| -------- | ---------------- |
| Database | **Neon** Postgres (or local Postgres) — `DATABASE_URL` in `backend/.env` |
| Queue | **Redis** on `localhost:6379` |
| Auth | **Clerk** — keys in `frontend/.env.local` + JWKS in `backend/.env` |
| Email | **Resend** — optional for alerts |
| Snapshots | Local disk (`STORAGE_BACKEND=local`) or S3-compatible object storage |
| Toolchain | Python 3.12+, Node.js 20+, a Playwright Chromium install for JS rendering / screenshots |

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

**Production:** set `APP_ENV=production` and pin `SECRET_KEY` / `INTERNAL_API_TOKEN` to real values. Outside development the API refuses to start if either is missing or still holds a placeholder — and `Base.metadata.create_all()` is skipped, so schema changes come only from Alembic.

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
| Digest | `python -m app.digest_job --loop` | Sends daily/weekly workspace digests |
| Retention | `python -m app.retention_job` | Purges snapshots (default 30 days) and runs (default 90 days) |

These are separate processes. Run them on a schedule/cron.

**Helpers:**

```powershell
# Windows PowerShell: full stack (loads backend\.env, API :8002; launches background jobs, logs to data\logs)
powershell -File .\scripts\restart-stack.ps1

# WSL2: transient systemd stack (API :8002, workers, scheduler; uses repo in-place)
wsl -e bash scripts/run-wsl-stack.sh

# WSL2: persistent systemd units (auto-restart on WSL boot)
wsl -e bash scripts/install-wsl-units.sh
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

### Monitoring modes (9)

| Mode | What it watches |
| ------ | ----------------- |
| `page_content` | Detected main content (falls back to whole-page text); `js_required` for SPAs |
| `site_links` | Sitemap URL-set changes (plain HTTP only) |
| `rss_feed` | RSS/Atom feed entries (plain HTTP only) |
| `readme` | GitHub repository README changes via `owner/repo` or full URL — GitHub-style markdown diffs; hits the GitHub API first (1 request, `ref`-pinned to the `/tree/<branch>` branch when one is parsed, else the repo's default branch), then a bounded raw fallbacks fan-out capped by a wall-clock budget | |
| `product_price` | Price + currency (defaults to a daily schedule) |
| `list_items` | Link list under a CSS selector |
| `json_field` | A single value via a JSONPath-style query, e.g. `$.data.price` |
| `visual` | Perceptual screenshot comparison — DCT pHash, `VISUAL_PHASH_THRESHOLD=8` bits of 256 (legacy aHash path keeps `VISUAL_AHASH_THRESHOLD=5`); the change detail renders the two compared runs as a before/after slider plus a collapsible pHash summary |
| `security_scan` | Cloudflare URL Scanner verdict + technology inventory, diffed item-by-item; needs `CLOUDFLARE_URLSCANNER_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`; plain HTTP only — big reference: [docs/guides/monitoring-modes.md](docs/guides/monitoring-modes.md) |

Also on the monitoring side: a **visual element picker** (point-and-click CSS-selector synthesis with sanitized proxied preview + brand/info auto-fill — `frontend/src/components/selector-picker.tsx`), opt-in **screenshots** captured only on signal changes (`visual` monitors are the exception: each run keeps its own capture under `screenshots/<monitor_id>/<run_id>.png` so the before/after pair matches the run that fired), **watch notes** and **monitor tags** (up to 10, API + bulk import only), **bulk CSV/JSON import/export** with sitemap-driven batch creation, **adaptive scheduling** that stretches intervals after quiet runs, and a public **status badge** (`GET .../badge.svg`, no auth).

### Change intelligence

| Area | What's included |
| ------ | ----------------- |
| Diffs | GitHub-style added/removed line views for every content change (unified + split), plus readable markdown views for list/price/value modes |
| AI summaries | Optional plain-language summaries per change — heuristic by default; any OpenAI-compatible gateway via `LLM_API_BASE` (default `api.kilo.ai`), toggled per workspace via `ai_summaries_enabled` |
| SubQ System 1 triage | Optional fast decision model via SubQ Decisions API (`SUBQ_ENABLED=true`, `subq-snap-preview`) — acts as a fast Stage 1 decision gate: probabilistic noise rejection, calibrated category classification, and impact scoring before LLM summarization |
| LLM providers & catalog | One OpenAI-compatible provider: Kilo Gateway (free models, default) — any other OpenAI-compatible gateway can be used via `LLM_API_BASE`; `GET /api/v1/model-catalog` feeds the settings UI and drives server-side failover with per-model probe status. The shipped Kilo list is a **probe ranking**, not a copy of the provider's marketing list: each model was run against the app's real prompt at the 200- and 800-token caps and ranked by whether it returns complete JSON, so the notes carry the evidence (and the cap it needs). Default `poolside/laguna-s-2.1:free` is currently the only model clean at the default cap; the rest need 800 tokens and/or are rate limited, empty, or reject structured output |
| AI relevance filter | Optional per-monitor `watch_note` triage: the LLM scores each diff vs. the note; routine noise is marked `is_noise=true`, held (not deleted), and excluded from notifications/digests; fails open on LLM error |
| Semantic triggers | Plain-English per-monitor trigger rules evaluated alongside thresholds |
| Conditional alerting | Optional per-monitor `alert_config` JSONB — `price_below`/`price_above` + `percent_change`, `list_min_added`/`list_min_removed`, `min_diff_chars`, `regex_must_match`/`regex_must_not_match`; unmet thresholds mark the change `is_noise=true` with a stored reason; empty config = alert on any hash difference |
| Change Q&A | Ask a question about any change from the detail page (`POST /changes/{id}/ask-ai`, 5/minute) |
| Alerts inbox | Every change stored in-app with `is_read` / `is_noise` state, independent of external notifications — Signal / Unread / Noise filters |

### Alerting & delivery

| Area | What's included |
| ------ | ----------------- |
| Alert channels | Email (Resend), Slack webhook, Discord webhook — with per-channel Send-test buttons |
| Outbound webhooks | HMAC-signed (`X-MTW-Signature`) deliveries with delivery log + exponential backoff; secrets encrypted at rest |
| Outbox reliability | Atomic outbox/webhook claiming with attempt caps; a reaper re-enqueues abandoned rows — no double-sends after retries |
| Digests | Daily / weekly workspace digest emails (background `digest_job`) — noise excluded |
| Failure alerts | Notifications fire after N consecutive check failures (`CONSECUTIVE_FAILURE_NOTIFY_THRESHOLD`) |

### Data, exports & observability

| Area | What's included |
| ------ | ----------------- |
| Workspace run logs | The **Logs** page lists every check run with outcome (`all`/`success`/`failed`/`changed`) and monitor/date filters (`GET /api/v1/workspaces/{id}/runs`), refreshed on a 15s cadence |
| Check-history export | `GET /api/v1/workspaces/{id}/export/runs?format=csv\|json` honours the same filters (20k-run cap) and writes an audit entry |
| Live monitor detail | SSE stream per monitor: 1-hour lifetime, 15s heartbeats, Redis ORM-wakeup hints so worker/scheduler/reaper transitions surface instantly; degrades to a 1.5s poll tick without Redis, with frontend reconnect backoff + stall detection |
| Dashboard activity | Change-activity card (7/14/30-day ranges, trend vs. prior period, stacked bars): `GET /changes/activity?days=14&include_noise=false` |
| Metrics | Prometheus-compatible counters at `GET /metrics` — monitor totals, runs/changes in 24h, outbox/webhook backlog |

### Platform

| Area | What's included |
| ------ | ----------------- |
| RBAC & audit | Owner / admin / member / viewer roles, member management, audit log |
| Teams | Expiring multi-use invite links (`/invite/{token}`) + workspace switching |
| API keys | `mtw_...` bearer tokens for programmatic access |
| Plans / billing | Free / pro / business / enterprise tiers, per-workspace usage quotas; Stripe checkout or simulated (solo: skip Stripe) |
| Keys: managed or BYO | Server defaults (`LLM_API_*`, `RESEND_API_KEY`) — or each workspace brings its own per-service keys and overrides the global |
| Public share pages | Opaque-token read-only page per monitor (`/share/{token}` — unguessable, hashed at rest, expiring, no login), edge-cached by the `share-cache` Worker |
| Brand-aware dashboard | Adding a website auto-fills logo/title/description/hero from page meta and re-hosts via `brand-assets/`; inbox items carry `monitor_brand` with favicon fallback |
| Retention | Background `retention_job` purges snapshots (default 30 days) and runs (default 90 days); change events survive run cleanup (migration `015`) — `docs/local-dev.md` §13 is the source of truth |
| Security | SSRF-pinned fetcher with redirect re-validation and domain guard, ReDoS/size-capped regexes, CSS selectors (300 chars) and URLs (2048 chars) at the schema + bulk-import layer, HKDF-purposed crypto (share tokens / API keys / Fernet keys), Gitleaks + a full threat model in [docs/security/threat-model.md](docs/security/threat-model.md) |

### Cloudflare free tier (optional, every piece optional, all $0)

See [docs/guides/cloudflare-free-features.md](docs/guides/cloudflare-free-features.md). Raw snapshots in R2; Browser Rendering **failover** Worker for `js_required` fetches (`workers/browser-failover/`, covered by `backend/tests/test_browser_failover.py` — local Playwright stays primary to preserve the ~10 min/day edge-browser quota); `security_scan` backed by the URL Scanner; screenshots servable from a public R2 bucket over a custom domain (`NEXT_PUBLIC_SCREENSHOT_CDN_URL`); edge caching for share pages (`workers/share-cache/`); optional cookie-less Web Analytics beacon on the UI.

### User interface

The web UI (Next.js) exposes: **Dashboard** (with change-activity card), **Monitors** (list / new / edit / detail with search, mode-filter, status tabs, sorting, bulk pause/resume, mode-specific snapshot previews including rich Cloudflare URL Scanner verdicts, non-blocking preview loading, and live brand asset re-scraping), **Logs** (workspace-wide run history + CSV export), **Changes** (per-change diff — text diffs for content modes, a run-keyed before/after screenshot slider plus collapsible pHash details for `visual` monitors), **Alerts** (inbox with toast notifications), **Import** (bulk CSV/JSON), **Settings** (channels, workspace keys, API keys/webhooks, digest preferences — with one-click copy for one-time secrets and developer workspace tooling tucked behind an Advanced card), and an in-app **Docs** page — plus a live header clock and an onboarding checklist (first monitor → baseline → channel). Results surface as toasts, and status/error boxes carry `role="status"`/`role="alert"` with `aria-describedby` hints. Styled with a Cohere-inspired design system (`frontend/src/app/globals.css`): 22px cards, pill buttons, `#1863dc` interaction blue, Space Grotesk display + Inter body, charcoal dark mode, sliding nav indicator.

## Tests & linting

```powershell
# Backend (Python / venv on Windows or WSL2)
cd backend
.\.venv\Scripts\ruff check app tests
.\.venv\Scripts\ruff format --check app tests
.\.venv\Scripts\python -m pytest tests -q -m "not integration"
# (or in WSL2: wsl -e bash -c "cd /mnt/c/.../backend && .venv/bin/pytest")

# Frontend (Bun or Node / npm)
cd ..\frontend
bun run lint      # or: npm run lint (tsc --noEmit && eslint .)
bun run test      # or: npm test (vitest run)
bun run build     # or: npm run build
```

CI (`.github/workflows/ci.yml`) runs the backend unit tests and the Postgres-backed integration tests in separate jobs, plus a Gitleaks secret scan, and the frontend type-check / lint / test / build.
