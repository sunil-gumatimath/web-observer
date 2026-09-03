<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Local development **without Docker**

You need:

1. **Python 3.11+** (3.12 fine)
2. **Node.js 20+**
3. **PostgreSQL** — **Neon** cloud URL or local install
4. **Redis** (local install / WSL / Memurai)

No Docker, no MinIO required. Snapshots go to `./data/snapshots`.

---

## Port alignment (important)

| Service | Default in this doc | Notes |
|---------|---------------------|--------|
| Frontend | `3000` | `npm run dev` |
| API | `8002` | Match `NEXT_PUBLIC_API_BASE_URL` |
| Redis | `6379` | Required for workers |

If the UI shows **Failed to fetch**, the API is not listening or the frontend URL/port is wrong.

---

## 1. Database & Redis

### Neon (recommended for this project)

Set in `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://USER:PASS@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

No local Postgres required. Neon can sleep when idle; first request may be slow.

### Local Postgres (optional)

```sql
CREATE USER monitor WITH PASSWORD 'monitor';
CREATE DATABASE web_observer OWNER monitor;
```

```env
DATABASE_URL=postgresql+psycopg://monitor:monitor@localhost:5432/web_observer
```

### Redis

- WSL2 / Memurai / Scoop Redis  
- Default: `redis://localhost:6379/0`

---

## 2. Backend env

```powershell
cd backend
# copy from example if needed; prefer real Neon URL
# DATABASE_URL, REDIS_URL, STORAGE_BACKEND=local, INTERNAL_API_TOKEN, Clerk JWKS
```

`APP_ENV` controls schema bootstrap: default `development`; dev values `development`/`dev`/`local`/`test`/`testing` auto-create tables via `create_all` (see `app/main.py` lifespan), `production`/`staging` require `alembic upgrade head`. Set `APP_ENV=production` in prod.

---

## 3. Backend venv + deps

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

Playwright Chromium is **required** for `js_required` monitors (checks routed to the Playwright browser queue).

---

## 4. Start the stack (5 processes)

Preferred on Windows — one command launches all 5 processes hidden (API :8002, HTTP+notifications worker, browser worker, scheduler, frontend :3000):

```powershell
powershell -File .\scripts\restart-stack.ps1
```

Relaunch kills anything on ports `8002`/`3000` first; per-process logs go to `data\logs` (`api.log`, `worker-http.log`, `worker-browser.log`, `scheduler.log`, `frontend.log`, plus `*_err.log`).

Or start each process manually (working directory: `backend`, except frontend):

```powershell
# 1 — API (port must match frontend NEXT_PUBLIC_API_BASE_URL)
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8002

# 2 — HTTP + notifications
.\.venv\Scripts\dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2

# 3 — Browser / JS-rendered checks (Playwright) — REQUIRED for js_required monitors
# Windows: always --threads 1 (sync Playwright is not multi-thread safe)
.\.venv\Scripts\dramatiq app.workers --queues browser_checks --processes 1 --threads 1

# 4 — Scheduler (scheduled checks; manual Run now works without it)
.\.venv\Scripts\python -m app.scheduler
```

**Playwright isolation:** screenshots and JS fetches run in a **subprocess** (`app.services.playwright_job`) so Dramatiq cannot share broken pipes with Chromium. Without this, Windows often fails with:

`Screenshot failed: [Errno 9] Bad file descriptor`

Digest and retention loops are **not** part of the launcher — run them manually when needed:

```powershell
.\.venv\Scripts\python -m app.digest_job --loop
.\.venv\Scripts\python -m app.retention_job
```

Then frontend (if not using the launcher):

```powershell
cd frontend
# NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002
bun run dev --port 3000
```

| URL | What |
|-----|------|
| http://127.0.0.1:3000 | UI |
| http://127.0.0.1:8002/docs | API docs |
| http://127.0.0.1:8002/health | API process |
| http://127.0.0.1:8002/ready | DB connectivity |

Tables are auto-created only when APP_ENV is development/test/testing (see app/main.py lifespan); production schema is managed by Alembic migrations. Set APP_ENV=production in prod and run `alembic upgrade head`.
---

## 5. Frontend env

`frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002
NEXT_PUBLIC_INTERNAL_API_TOKEN=dev-internal-token
# Optional: preselect a dev/seed workspace in the UI (internal-token mode only)
# NEXT_PUBLIC_DEV_WORKSPACE_ID=
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

With Clerk keys set, the app requires **sign-in**; it will not fall back to the internal token for API calls.

1. Sign in via Clerk  
2. Create a monitor  
3. **Run now** (first success = baseline, no alert)

---

## 6. Minimum set

| Process | Required? |
|---------|-----------|
| Redis | Yes (queue + rate limits) |
| DB (Neon or local) | Yes |
| API (`uvicorn`) | Yes |
| Worker HTTP + notifications | Yes for checks/alerts |
| Worker browser (`threads 1`) | Yes for `js_required` monitors |
| Scheduler | Yes for schedules; optional for manual Run now |
| Frontend | Yes for UI |
| MinIO / Docker | **No** |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| **Failed to fetch** | API down or wrong port; start API; match `NEXT_PUBLIC_API_BASE_URL` |
| Stuck **Loading…** | Sign in with Clerk; hard-refresh; ensure API up |
| Hydration `rtrvr-ls` warning | Browser extension (Retriever); suppress or disable on localhost |
| Can't connect to DB | Neon awake? `sslmode=require`? `postgresql+psycopg://`? |
| Dramatiq / Redis errors | Start Redis; `REDIS_URL=redis://localhost:6379/0` |
| Visual: Bad file descriptor | Browser worker `--threads 1`; restart workers; Playwright install chromium |
| Visual: Executable doesn't exist | `python -m playwright install chromium` |
| Snapshot storage errors | `STORAGE_BACKEND=local` |
| Frontend CORS | API allows `localhost:3000` and `127.0.0.1:3000` |

---

## Unit tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q -m "not integration"
```
