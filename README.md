<p align="center">
  <img src="assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Web Observer

> Tell me when the web pages I care about change — and clearly explain what changed.

Web Observer is a web change-detection and alerting platform. You create a monitor; workers check it on a schedule, hash what they see, and notify you only when a change matters.

[Architecture](#architecture) · [Quick start](#quick-start) · [Documentation](docs/) · [Roadmap](docs/roadmap.md)

## Highlights

- **10 monitoring modes** — page content (including `js_required` SPAs), sitemaps, RSS/Atom, GitHub READMEs, prices, CSS-selector lists, JSON values, visual screenshots, Cloudflare security scans, and HTML/meta facts.
- **Signal, not spam** — content-hash and perceptual-image diffs, conditional thresholds, watch-note AI triage, noise marking, adaptive intervals, and an alerts inbox.
- **Reliable delivery** — email (Resend), Slack, Discord, HMAC-signed webhooks, and in-app alerts, driven by an outbox with bounded retries.
- **Runs anywhere** — local processes against hosted Neon Postgres and local Redis, with opt-in $0 Cloudflare edge workers for failover fetching, share-page caching, and security verdicts.
- **Built for teams** — workspaces, RBAC, audit log, API keys, invite links, public share pages, and per-workspace BYO keys.

> **Status:** Phases 0–7 complete. Post-roadmap work added the alerts inbox, conditional thresholds, AI triage, Redis dedup caching, tags, run-log exports, brand enrichment, encrypted webhook secrets, and per-principal rate limits. Schema head: Alembic `015_change_run_set_null`. Test counts change as fixes land, so [CI](.github/workflows/ci.yml) is the source of truth.

## Architecture

One idea: **you watch pages, workers do the checking, and you get told only when something matters.**

Stack: **Next.js** (App Router, React 19, Clerk, Tailwind) → **FastAPI** → **Neon Postgres** + **Redis** (Dramatiq broker) → **Dramatiq workers** (HTTP / Playwright / notifications) → alert channels. Snapshots go to local disk or S3-compatible storage; Alembic owns the schema.

### At a glance

```mermaid
flowchart LR
    YOU["You / team"]
    UI["Next.js UI<br/>:3000 · Clerk"]
    API["FastAPI<br/>:8002 · REST + SSE"]
    PG[("Neon Postgres")]
    RD[("Redis queues")]
    SCHED["Scheduler"]
    W["Dramatiq workers<br/>HTTP · Playwright · AI · notify"]
    SRC["Monitored pages"]
    ST["Snapshots<br/>disk or S3/R2"]
    OUT["Resend · Slack · Discord<br/>signed webhooks · inbox"]
    AUTH["Clerk · JWT + JWKS"]
    EDGE["Cloudflare edge<br/>share cache · failover · URL Scanner"]

    YOU --> UI
    UI -->|REST + SSE| API
    API <--> AUTH
    API <--> PG
    API --> RD
    SCHED -->|claim due monitors| PG
    SCHED -->|enqueue checks| RD
    RD --> W
    W <--> PG
    W --> ST
    W --> SRC
    W --> OUT
    UI -.->|/share/| EDGE
    W -.->|opt-in| EDGE
    EDGE -.-> SRC
```

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

    subgraph Edge["Cloudflare edge — opt-in, free tier"]
        BF["browser-failover worker<br/>edge Chromium, retry path only<br/>(dormant where workers.dev is blocked)"]
        SCS["share-cache worker<br/>caches /share/ on the app hostname (routes + CACHE_HOST)"]
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

The full module diagram, ERD, and manual-run sequences live in [docs/architecture.md](docs/architecture.md).

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

## Documentation

| Doc | Topic |
| --- | --- |
| [docs/](docs/) | Documentation index |
| [docs/local-dev.md](docs/local-dev.md) | Run locally + operations reference (processes, secrets, retention) |
| [docs/architecture.md](docs/architecture.md) | Deep architecture: modules, ERD, manual-run + pipeline sequences |
| [docs/auth-modes.md](docs/auth-modes.md) | Auth modes (dev token / Clerk) |
| [docs/guides/clerk.md](docs/guides/clerk.md) | Clerk auth (dev setup + production hardening) |
| [docs/guides/resend-setup.md](docs/guides/resend-setup.md) | Email alerts |
| [docs/guides/cloudflare-free-features.md](docs/guides/cloudflare-free-features.md) | Cloudflare free tier end-to-end |
| [docs/guides/monitoring-modes.md](docs/guides/monitoring-modes.md) | The 10 monitoring modes, options, and limits |
| [docs/roadmap.md](docs/roadmap.md) | Feature roadmap (Phases 8–10) |
| [docs/security/threat-model.md](docs/security/threat-model.md) | Security policy: SSRF, tenant isolation, out of scope |
| [docs/adrs/](docs/adrs/) | Architecture decision records |
| [docs/integrations/n8n-zapier.md](docs/integrations/n8n-zapier.md) | n8n / Zapier automation |

## Quick start

### Prerequisites

| Piece | This project |
| --- | --- |
| Database | **Neon** Postgres (or local Postgres) — `DATABASE_URL` in `backend/.env` |
| Queue | **Redis** on `localhost:6379` |
| Auth | **Clerk** — keys in `frontend/.env.local`, JWKS in `backend/.env` |
| Email | **Resend** — optional for alerts |
| Snapshots | Local disk (`STORAGE_BACKEND=local`) or S3-compatible storage |
| Toolchain | Python 3.12+, Node.js 20+, Playwright Chromium for JS rendering / screenshots |

### 1. Configure environment

Secrets live in gitignored env files — never commit them.

`backend/.env` (minimum):

```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg://USER:PASS@HOST/neondb?sslmode=require
REDIS_URL=redis://localhost:6379/0
STORAGE_BACKEND=local
INTERNAL_API_TOKEN=dev-internal-token
SECRET_KEY=change-me-in-production
CLERK_JWKS_URL=https://YOUR-INSTANCE.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://YOUR-INSTANCE.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...
```

- `APP_ENV` is not optional: an unset value is treated as non-development, so the production guards stay active.
- Use `postgresql+psycopg://`, not plain `postgresql://`.
- Pin `SECRET_KEY` / `INTERNAL_API_TOKEN` in production. A random restart value makes stored workspace keys unreadable and invalidates every `mtw_` API key.
- In production (`APP_ENV=production`) the API refuses placeholder secrets and skips `create_all`; schema comes only from Alembic: `cd backend && alembic upgrade head`.

Full backend variable list: [.env.example](.env.example).

`frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002
NEXT_PUBLIC_INTERNAL_API_TOKEN=dev-internal-token
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
# Optional: NEXT_PUBLIC_DEV_WORKSPACE_ID=
# Optional: NEXT_PUBLIC_CF_BEACON_TOKEN=
# Optional: NEXT_PUBLIC_SCREENSHOT_CDN_URL=https://screenshots.example.com
```

`NEXT_PUBLIC_API_BASE_URL` must match the API port you start. Full frontend list: [frontend/.env.example](frontend/.env.example).

### 2. Install (one time)

Linux / macOS:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # JS rendering / screenshots
cd ../frontend && npm ci
```

Windows (PowerShell):

```powershell
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cd ..\frontend; npm ci
```

`npm ci` is CI-canonical (`bun install` also works). Python 3.12+ and Node.js 20+.

### 3. Run the stack

Redis must be running. Start these processes from `backend/` (the frontend one from `frontend/`):

| # | Process | Command |
| --- | --- | --- |
| 1 | API | `uvicorn app.main:app --host 127.0.0.1 --port 8002` |
| 2 | HTTP + notification worker | `dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2` |
| 2b | AI enrichment worker | `dramatiq app.workers --queues ai_enrichment --processes 1 --threads 1` |
| 3 | Browser worker | `dramatiq app.workers --queues browser_checks --processes 1 --threads 1` |
| 4 | Scheduler | `python -m app.scheduler` |
| 5 | Frontend | `npm run dev` (port 3000) |

The browser worker is required for `js_required` monitors and opt-in screenshots. Use `--threads 1` on Windows; Playwright runs in a subprocess to avoid `[Errno 9] Bad file descriptor`.

Optional jobs, on a schedule/cron: `python -m app.digest_job --loop` (daily/weekly digests) and `python -m app.retention_job` (purge old snapshots/runs).

Docker alternative — one container with everything inside:

```bash
./scripts/docker-up.sh              # build + start (API :8002, frontend :3000, workers, scheduler, redis)
./scripts/docker-up.sh down         # stop
./scripts/docker-up.sh logs -f      # follow logs
./scripts/docker-up.sh ps           # container status
```

| URL | What |
| --- | --- |
| <http://127.0.0.1:3000> | UI |
| <http://127.0.0.1:8002/docs> | API docs |
| <http://127.0.0.1:8002/health> | API up? |
| <http://127.0.0.1:8002/ready> | DB reachable? |
| <http://127.0.0.1:8002/metrics> | Prometheus metrics |

"Failed to fetch" in the UI means the API is down or `NEXT_PUBLIC_API_BASE_URL` does not match its port.

### 4. First check

1. Open <http://127.0.0.1:3000> → **Sign up / Sign in** (Clerk).
2. **Settings → Alert channels** → add your email (optional).
3. **New monitor** → e.g. `https://example.com/` (enable screenshots for image history).
4. Open the monitor → **Run now**. The first success is the baseline, so no alert fires.

## Features

### Monitoring modes

| Mode | What it watches |
| --- | --- |
| `page_content` | Detected main content (falls back to whole-page text); `js_required` for SPAs |
| `site_links` | Sitemap URL-set changes (plain HTTP only) |
| `rss_feed` | RSS/Atom feed entries (plain HTTP only) |
| `readme` | GitHub README changes via `owner/repo` or URL; GitHub API first, then bounded raw fallbacks |
| `product_price` | Price + currency (daily schedule by default) |
| `list_items` | Link list under a CSS selector |
| `json_field` | A single JSONPath-style value, e.g. `$.data.price` |
| `visual` | Perceptual screenshot comparison — 256-bit pHash, threshold 8; before/after slider |
| `security_scan` | Cloudflare URL Scanner verdict + tech inventory; needs API token (plain HTTP only) |
| `html_meta` | Title, meta tags, canonical/alternate URLs, JSON-LD types, script srcs (plain HTTP only) |

Also: a visual element picker (point-and-click CSS-selector synthesis), opt-in screenshots on signal changes (every run for `visual` monitors), watch notes, up to 10 tags per monitor, bulk CSV/JSON import/export with sitemap batch creation, adaptive scheduling after quiet runs, and a public status badge (`GET .../badge.svg`, no auth — the monitor UUID in the URL is the capability token). Details and limits: [docs/guides/monitoring-modes.md](docs/guides/monitoring-modes.md).

### Change intelligence

| Area | What's included |
| --- | --- |
| Diffs | GitHub-style added/removed line views (unified + split), plus readable views for list/price/value modes |
| AI summaries | Optional plain-language summaries; heuristic by default, any OpenAI-compatible gateway via `LLM_API_BASE`; catalog at `GET /api/v1/model-catalog` |
| Fast triage | Optional SubQ Decisions gate (`SUBQ_ENABLED`) for noise rejection, category, and impact scoring before LLM summarization |
| Relevance filter | Per-monitor `watch_note` triage; routine noise is marked `is_noise=true`, held in the inbox, and excluded from notifications/digests; fails open on LLM error |
| Semantic triggers | Plain-English per-monitor trigger rules evaluated alongside thresholds |
| Conditional alerting | Per-monitor `alert_config` JSONB: `price_below`/`price_above` + `percent_change`, `list_min_added`/`list_min_removed`, `min_diff_chars`, regex must/must-not-match. Oversized, unparseable, or >50 ms regexes suppress with an explicit reason |
| Controls | Daily notification quotas per plan plus a 60-minute cooldown between failure notices |
| Change Q&A | Ask a question about any change (`POST /changes/{id}/ask-ai`, 5/minute) |
| Alerts inbox | Every change stored in-app with `is_read` / `is_noise` state — Signal / Unread / Noise filters |

### Alerting & delivery

| Area | What's included |
| --- | --- |
| Channels | Email (Resend), Slack webhook, Discord webhook, each with a Send-test button |
| Webhooks | HMAC-signed (`X-MTW-Signature`) deliveries with log and exponential backoff; secrets encrypted at rest |
| Outbox | Atomic outbox/webhook claiming with attempt caps and an abandoned-row reaper — no double-sends after retries |
| Digests | Daily / weekly workspace digest emails, noise excluded |
| Failure alerts | Notification after N consecutive check failures (`CONSECUTIVE_FAILURE_NOTIFY_THRESHOLD`) |

### Data & observability

| Area | What's included |
| --- | --- |
| Run logs | Workspace-wide Logs page with outcome and monitor/date filters (`GET /api/v1/workspaces/{id}/runs`), 15s refresh |
| Export | `GET /api/v1/workspaces/{id}/export/runs?format=csv\|json` with the same filters (20k cap, audited) |
| Live detail | Per-monitor SSE: 1-hour lifetime, 15s heartbeats, Redis wakeup hints; degrades to a 1.5s poll without Redis |
| Activity | Change-activity card (7/14/30-day ranges, trend vs prior period) via `GET /changes/activity` |
| Metrics | Prometheus counters at `GET /metrics` — monitor totals, 24h runs/changes, outbox/webhook backlog |

### Platform & security

| Area | What's included |
| --- | --- |
| Teams | Owner / admin / member / viewer roles, member management, audit log, expiring invite links, workspace switching |
| API access | `mtw_...` bearer tokens for programmatic use |
| Plans | Free / pro / business / enterprise tiers with per-workspace quotas; Stripe checkout or simulated (solo: skip Stripe) |
| Keys | Server defaults (`LLM_API_*`, `RESEND_API_KEY`) or per-workspace BYO overrides |
| Share pages | Opaque-token read-only `/share/{token}` pages (unguessable, hashed at rest, expiring, no login) |
| Brand-aware UI | Auto-fills logo/title/description/hero from page meta and re-hosts assets; inbox items carry favicon fallback |
| Retention | Snapshots purged after 30 days, runs after 90 days; change events survive run cleanup (migration `015`) |
| Security | SSRF-pinned fetcher with redirect re-validation, ReDoS/size-capped regexes, input length limits, HKDF-purposed crypto, [threat model](docs/security/threat-model.md) |

### Cloudflare free tier (optional)

Everything below is opt-in and inactive until configured: R2 snapshots (`STORAGE_BACKEND=s3`), Browser Rendering **failover** for `js_required` fetches (local Playwright stays primary), URL Scanner for `security_scan`, R2 screenshot CDN (`NEXT_PUBLIC_SCREENSHOT_CDN_URL`), and cookie-less Web Analytics (`NEXT_PUBLIC_CF_BEACON_TOKEN`). The `share-cache` Worker is active on the app hostname (`app.sunilted.qzz.io/share/*`, with `CACHE_HOST`). Full setup: [docs/guides/cloudflare-free-features.md](docs/guides/cloudflare-free-features.md).

Monitor previews are snapshots from the last successful check, not live views. With `STORAGE_BACKEND=local` the files live on the machine that ran the check; moving the database needs fresh runs (or S3 storage). Bot-protected, login-only, and private-network URLs can fail even if the monitor was accepted — see [fetch reliability](docs/guides/monitoring-modes.md#fetch-reliability-and-previews).

## Tests & linting

Linux / macOS:

```bash
cd backend && source .venv/bin/activate
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
.venv/bin/python -m pytest tests -q -m "not integration"
# Integration tests need TEST_DATABASE_URL pointing at a real Postgres:
# .venv/bin/python -m pytest tests -q -m "integration"

cd ../frontend
npm run lint      # tsc --noEmit && eslint .
npm test          # vitest run
npm run build
```

Windows (PowerShell):

```powershell
cd backend
.\.venv\Scripts\ruff check app tests
.\.venv\Scripts\ruff format --check app tests
.\.venv\Scripts\python -m pytest tests -q -m "not integration"
cd ..\frontend
npm run lint; npm test; npm run build
```

[CI](.github/workflows/ci.yml) runs backend unit + Postgres-backed integration tests, Gitleaks, and frontend type-check / lint / test / build in separate jobs. It is the source of truth for required checks and current counts.

## Contributing

`main` is protected by a repository ruleset (`.github/rulesets/main.json`): no force-push or branch deletion, and every change lands through a PR with all five CI jobs green. No approving review is required, but CodeRabbit comments must be addressed or resolved before merging.

```bash
git switch -c my-change
# ... commit ...
git push -u origin my-change
gh pr create --fill
gh pr checks --watch
```

After editing the ruleset JSON, re-apply it:

```bash
gh api --method PUT repos/sunil-gumatimath/web-observer/rulesets/27852901 \
  --input .github/rulesets/main.json
```
