# Web Observer

Web change-detection and alerting platform.

> Tell me when the web pages I care about change and clearly explain what changed.

## Status

Phases **0–7** core complete. Billing is optional (solo use: skip Stripe).

| Doc | Topic |
|-----|--------|
| [docs/local-dev.md](docs/local-dev.md) | Run without Docker (full process list) |
| [docs/clerk-setup.md](docs/clerk-setup.md) | Clerk auth |
| [docs/resend-setup.md](docs/resend-setup.md) | Email alerts |
| [docs/phase-3.md](docs/phase-3.md) | JS / Playwright / browser queue |
| [docs/phase-4.md](docs/phase-4.md) | Structured + visual modes |
| [docs/phase-6-7.md](docs/phase-6-7.md) | Plans, webhooks, API keys |
| [docs/architecture-uml.md](docs/architecture-uml.md) | Architecture diagrams |
| `web-observer-final-roadmap.md` | Original product roadmap (historical) |

## How monitoring works (short)

1. You create a monitor (URL + mode).  
2. Worker fetches the page (HTTP or Playwright) and builds a content hash.  
3. First success = **baseline** (no alert).  
4. Later hash differs → save diff → notify (email / Slack / Discord / webhook).  

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
3. **New monitor** → e.g. `https://example.com/` (or Visual for screenshots).  
4. Open monitor → **Run now** (first success = baseline, no alert).  

## Optional features

| Feature | Notes |
|---------|--------|
| JS / visual monitors | Playwright + `browser_checks` worker (`--threads 1`) |
| AI summaries | Heuristic by default; set `LLM_API_KEY` for LLM |
| API keys / webhooks | Settings |
| Alerts inbox / watch notes | In-app alerts + monitor notes |

## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q -m "not integration"
```

## Stack

Python / FastAPI · Neon Postgres · Redis / Dramatiq · Next.js · Clerk · Resend · local disk snapshots · Playwright
