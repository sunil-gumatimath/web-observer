# Web Observer

Web change-detection and alerting platform.

> Tell me when the web pages I care about change and clearly explain what changed.

## Status

Phases **0–7** core complete. Billing is optional (solo use: skip Stripe).

| Doc | Topic |
|-----|--------|
| [docs/local-dev.md](docs/local-dev.md) | Run without Docker |
| [docs/clerk-setup.md](docs/clerk-setup.md) | Clerk auth |
| [docs/resend-setup.md](docs/resend-setup.md) | Email alerts |
| [docs/phase-6-7.md](docs/phase-6-7.md) | Plans, webhooks, API keys |
| `web-observer-final-roadmap.md` | Original roadmap |

## How monitoring works (short)

1. You create a monitor (URL + mode).  
2. Worker fetches the page and builds a content hash.  
3. First success = **baseline** (no alert).  
4. Later hash differs → save diff → **email via Resend**.  

## What you need

| Piece | This project |
|--------|----------------|
| Database | **Neon** (Postgres) — set `DATABASE_URL` in root `.env` |
| Queue | **Redis** on `localhost:6379` |
| Auth | **Clerk** — keys in `frontend/.env.local` + backend JWKS in root `.env` |
| Email | **Resend** — `RESEND_API_KEY` + `EMAIL_FROM=onboarding@resend.dev` |
| Snapshots | Local disk (`STORAGE_BACKEND=local`) — no MinIO |
| Docker | **Not required** |

Billing / Stripe: **skip** for solo use. Free plan is generous enough.

## Env files (do not commit secrets)

**Root `.env`** (backend):

```env
DATABASE_URL=postgresql+psycopg://USER:PASS@HOST/neondb?sslmode=require
REDIS_URL=redis://localhost:6379/0
STORAGE_BACKEND=local
INTERNAL_API_TOKEN=dev-internal-token

RESEND_API_KEY=re_...
EMAIL_FROM=onboarding@resend.dev

CLERK_JWKS_URL=https://YOUR-INSTANCE.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://YOUR-INSTANCE.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...
```

Use `postgresql+psycopg://` (not plain `postgresql://`) for this app.

**Frontend `frontend/.env.local`:**

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

Clerk keys: `cd frontend` → `clerk env pull` (if linked).  
Backend JWKS: `node scripts/wire-clerk-backend.mjs`

## Run locally (no Docker)

### One-time

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd ..\frontend
npm install
```

### Every time (4 terminals)

**1 — API**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

**2 — Worker** (checks + email)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2
```

**3 — Scheduler** (optional if you only use “Run now”)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.scheduler
```

**4 — Frontend**

```powershell
cd frontend
npm run dev
```

Or: `.\scripts\run-local.ps1` then start the frontend.

| URL | What |
|-----|------|
| http://localhost:8000/docs | API |
| http://localhost:8000/ready | DB (Neon) OK? |
| http://localhost:3000 | UI |

## First test flow

1. Open http://localhost:3000 → **Sign up / Sign in** (Clerk).  
2. **Settings → Alert channels** → add your email.  
3. **New monitor** → e.g. `https://example.com/`.  
4. Open monitor → **Run now** (first success = baseline, no email).  
5. Optional email-only test:

```powershell
cd backend
.\.venv\Scripts\python scripts\send_test_email.py --to you@example.com
```

## Optional features

| Feature | Notes |
|---------|--------|
| JS / visual monitors | Playwright + browser worker queue |
| AI summaries | Heuristic by default; set `LLM_API_KEY` for LLM |
| API keys / webhooks | Settings (no paid plan required for solo) |
| Docker | `docker compose up --build` if you want it later |

## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q -m "not integration"
```

## Stack

Python / FastAPI · Neon Postgres · Redis / Dramatiq · Next.js · Clerk · Resend · local disk snapshots · Playwright (optional)
