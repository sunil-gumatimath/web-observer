# Web Observer

Web change-detection and alerting platform.

> Tell me when the web pages I care about change and clearly explain what changed.

## Status

**Phases 0–7 complete.** The original roadmap has been exceeded — the DB schema is at migration `006_alerts` (post-roadmap work added a storage optimization, the alerts inbox, and monitor watch notes). Billing is optional (solo use: skip Stripe).

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
DATABASE_URL=postgresql+psycopg://USER:PASS@HOST/neondb?sslmode=require
REDIS_URL=redis://localhost:6379/0
STORAGE_BACKEND=local
INTERNAL_API_TOKEN=dev-internal-token

CLERK_JWKS_URL=https://YOUR-INSTANCE.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://YOUR-INSTANCE.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...
```

Use `postgresql+psycopg://` (not plain `postgresql://`).

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
npm install
```

### Every time (5 processes)

Redis must already be running. Prefer loading env from `backend/.env` (Neon).

| # | Process | Command |
|---|---------|---------|
| 1 | **API** | `uvicorn app.main:app --host 127.0.0.1 --port 8002` |
| 2 | **HTTP worker** | `dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2` |
| 3 | **Browser worker** | `dramatiq app.workers --queues browser_checks --processes 1 --threads 1` |
| 4 | **Scheduler** | `python -m app.scheduler` |
| 5 | **Frontend** | `npm run dev` (port 3000) |

**Browser worker is required** for `visual` mode and `js_required` monitors.  
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
| Monitoring modes | `page_content` (whole page text), `site_links` (sitemap URL changes), `product_price` (price/currency), `list_items` (CSS-selector link list) — plus `js_required` for SPAs |
| Alert channels | Email (Resend), Slack webhook, Discord webhook |
| AI summaries | Heuristic by default; optional OpenAI-compatible LLM for category + plain-language summary |
| Diffs | Before/after text diffs; structured JSON / list diffs; optional screenshot change gate |
| Screenshots | Per-monitor `screenshots_enabled`: Playwright screenshot history + side-by-side comparison with aHash distance, served via the existing storage layer |
| Outbound webhooks | Signed (`X-MTW-Signature`) deliveries on change events + delivery log |
| API keys | `mtw_...` bearer tokens for programmatic access |
| Bulk workflows | CSV / JSON import + export of monitors and changes |
| Alerts inbox | In-app unread/read alerts, `is_noise` flag to exclude from digests |
| Watch notes | Free-text notes per monitor |
| Digests | Daily / weekly workspace digest emails (background `digest_job`) |
| RBAC & audit | Owner / admin / member / viewer roles, member management, audit log |
| Plans / billing | free / pro / business / enterprise tiers; Stripe or simulated checkout (solo: skip Stripe) |
| Adaptive scheduling | Interval auto-stretches after quiet runs |
| Retention | Background `retention_job` purges old runs / snapshots (default 90 days) |
| Brand-aware dashboards | Auto-detected title/description/logo/hero per monitor; re-hosted brand assets on the dashboard and public share pages |
| Bring-your-own keys | Per-workspace LLM (api key/base/model) and Resend (api key + sender) overrides; falls back to global keys |
| Public share links | Opaque-token read-only share links for a monitor's change history (token hashed at rest, revocable) |
| Team invites | Opaque-token workspace invite links with role / max-uses / expiry (token hashed at rest) |
| Opt-in screenshots | `screenshots_enabled` captures a screenshot on every check (off by default to avoid forcing Playwright on text monitors) |

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

- **Brand-aware dashboards** — each monitor auto-detects a title, description, logo, and hero image (served via a public brand-asset endpoint so they render on the dashboard and the public share page). Trigger detection when creating a monitor or via the per-monitor *Brand* action.
- **Bring-your-own keys** — a workspace owner can set per-workspace LLM keys (`llm_api_key` / `llm_api_base` / `llm_model`) and Resend keys (`resend_api_key` / `email_from`) in **Settings → Workspace keys**. AI summaries and email alerts use the workspace keys when present, otherwise the global keys. Settings values are masked on read.
- **Public share links** — from a monitor's detail page, *Share* creates an opaque-token link (`/share/{token}`) that anyone can open to view the monitor's change history. The token is hashed at rest (only its prefix is stored) and the link is revocable.
- **Team invites** — **Settings → Team** generates opaque-token invite links with a role, max uses, and expiry. Tokens are hashed at rest.
- **Opt-in screenshots** — set `screenshots_enabled` on a monitor (UI: create monitor → screenshot option) to capture a screenshot on every check. Off by default so text monitors don't require Playwright.

> Database: the columns/tables for these features are applied by `backend/scripts/apply_007.py` (idempotent; run with `PYTHONPATH=.` from `backend/`). New tables are also auto-created by `Base.metadata.create_all` at API startup.
