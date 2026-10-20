<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Local development

You need:

1. **Python 3.11+** (3.12 fine)
2. **Node.js 20+**
3. **PostgreSQL** — **Neon** cloud URL or local install
4. **Redis** — local install / WSL / Memurai

Snapshots go to `./data/snapshots`.

---

## Port alignment (important)

| Service | Default in this doc | Notes |
| --------- | --------------------- | -------- |
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

- Redis — local install / WSL2 / Memurai / Scoop; default `redis://localhost:6379/0`

**Redis inside WSL2** (Windows host, Linux VM) needs two adjustments:

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| Every API request takes ~21 s; the log says `Rate limit storage unreachable - falling back to in-memory storage` | Windows resolves `localhost` to `::1` first, but WSL2 only forwards **IPv4** to the host, so each new connection stalls on the IPv6 attempt before falling back | Use the IPv4 literal: `REDIS_URL=redis://127.0.0.1:6379/0` |
| `Authentication required` / `NOAUTH Authentication required` | The WSL Redis has `requirepass` set | Put the password in the URL: `REDIS_URL=redis://:YOUR_PASSWORD@127.0.0.1:6379/0` |

Check the WSL side with `sudo grep -E '^\s*requirepass' /etc/redis/redis.conf`. If Windows→WSL forwarding breaks entirely, `wsl --shutdown` then `wsl` usually restores it.

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

Relaunch stops the processes **this stack** started (tracked in `data\logs\our-processes.txt`, plus anything running from this repo) and frees ports `8002`/`3000`; per-process logs go to `data\logs` (`api.log`, `worker-http.log`, `worker-browser.log`, `scheduler.log`, `frontend.log`, plus `*_err.log`).

**Port conflicts.** A port owned by *another* app is never killed — the stack moves to the next free port instead, and stays wired up: the API's `CORS_ORIGINS` gains the chosen frontend origin and the frontend's `NEXT_PUBLIC_API_BASE_URL` follows the API port. The script prints the URLs it actually bound.

```powershell
powershell -File .\scripts\restart-stack.ps1                      # auto-shifts if 3000/8002 are taken
powershell -File .\scripts\restart-stack.ps1 -FrontendPort 3100   # prefer a specific port
powershell -File .\scripts\stop-stack.ps1                         # stop only our processes
```

Note: Next.js auto-increments its port when the requested one is busy, so a *second* dev server on this machine can land on ours. The launcher detects that and retries on the next free port.

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
| ----- | ------ |
| <http://127.0.0.1:3000> | UI |
| <http://127.0.0.1:8002/docs> | API docs |
| <http://127.0.0.1:8002/health> | API process |
| <http://127.0.0.1:8002/ready> | DB connectivity |

Tables are auto-created only when APP_ENV is development/test/testing (see app/main.py lifespan); production schema is managed by Alembic migrations. Set APP_ENV=production in prod and run `alembic upgrade head`

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

## 6. Notable endpoints & behavior (post-roadmap additions)

| Capability | Endpoint / notes |
| ------------ | ------------------ |
| Change activity | `GET /api/v1/workspaces/{id}/changes/activity?days=14&include_noise=false` — per-day counts + per-category breakdown for the dashboard card (`days` 1–90, noise excluded by default, 20k-row cap, null category → `uncategorized`) |
| Run logs | `GET /api/v1/workspaces/{id}/runs` — workspace-wide check history with outcome (`all`/`success`/`failed`/`changed`), monitor and date filters; `backend/app/services/run_logs.py` is the shared filter source of truth |
| Runs export | `GET /api/v1/workspaces/{id}/export/runs?format=csv|json` — CSV/JSON export honouring the same filters as the logs list (20k-run cap, `runs.exported` audit entry) |
| Monitor SSE stream | `GET /api/v1/workspaces/{id}/monitors/{monitor_id}/stream` — run-status/change events; 1-hour lifetime, 15s heartbeat, Redis ORM-wakeup hints from `app/services/live_events.py` (candidates: pipeline, workers, scheduler, reaper). Without Redis the publisher circuit-breaks and the stream falls back to a 1.5s poll tick |
| Bulk pause / resume | `POST /api/v1/workspaces/{id}/monitors/pause-all`, `.../resume-all` (resume re-schedules `next_run_at`) |
| Selector preview | `POST /api/v1/workspaces/{id}/monitors/selector-preview` — sanitized HTML for the point-and-click picker |
| Brand info | `POST /api/v1/workspaces/{id}/monitors/brand-info` — logo/title/description auto-fill |
| Mark all read | `POST /api/v1/workspaces/{id}/alerts/read-all` |
| Snapshot download | `GET /api/v1/workspaces/{id}/snapshots/{snapshot_id}` |

Fetch behavior worth knowing while debugging:

- The SSRF-pinned fetcher tries **every** validated IP in turn — one dead CDN PoP won't fail a check; only connect-level errors trigger failover (`backend/app/services/fetcher.py:_pinned_get`).
- `readme` monitors hit the GitHub API first (resolves the default branch in 1 request), then fall back to capped raw probes.
- LLM summaries fail over across `LLM_FALLBACK_MODELS`; `none` disables failover. The catalog default is the model list of the provider that `LLM_API_BASE` points at (see `backend/app/services/model_catalog.py`).

Optional env (defaults work locally):

```env
LLM_API_KEY=            # empty => heuristic summaries only
LLM_API_BASE=https://api.kilo.ai/api/gateway
LLM_MODEL=poolside/laguna-s-2.1:free
LLM_FALLBACK_MODELS=    # empty => catalog default for the active provider; "none" => primary only

# Second OpenAI-compatible provider (Google Gemini) — active when
# LLM_API_BASE points at generativelanguage.googleapis.com
GEMINI_API_KEY=
GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai
GEMINI_MODEL=gemini-3.1-flash-lite

STORAGE_BACKEND=local   # set to s3 + endpoint/keys for GCS/R2-compatible storage
```

---

## 7. Minimum set

| Process | Required? |
| --------- | ----------- |
| Redis | Yes (queue + rate limits) |
| DB (Neon or local) | Yes |
| API (`uvicorn`) | Yes |
| Worker HTTP + notifications | Yes for checks/alerts |
| Worker browser (`threads 1`) | Yes for `js_required` monitors |
| Scheduler | Yes for schedules; optional for manual Run now |
| Frontend | Yes for UI |

---

## Troubleshooting

| Issue | Fix |
| ------- | ----- |
| **Failed to fetch** | API down or wrong port; start API; match `NEXT_PUBLIC_API_BASE_URL` |
| Stuck **Loading…** | Sign in with Clerk; hard-refresh; ensure API up |
| Hydration `rtrvr-ls` warning | Browser extension (Retriever); suppress or disable on localhost |
| Can't connect to DB | Neon awake? `sslmode=require`? `postgresql+psycopg://`? |
| Dramatiq / Redis errors | Start Redis; `REDIS_URL=redis://localhost:6379/0`; Windows→WSL forwarding flaps — `wsl --shutdown` then `wsl` |
| Limiter logs "storage unreachable - falling back" | Redis was down mid-traffic; rate limiting degraded to per-process in-memory (requests keep working, auto-recovers when Redis returns) — restart Redis |
| `429` responses | API rate limits are enforced (default 60/min per verified principal or IP, stricter on decorated endpoints); check `Retry-After` |
| Visual: Bad file descriptor | Browser worker `--threads 1`; restart workers; Playwright install chromium |
| Visual: Executable doesn't exist | `python -m playwright install chromium` |
| Snapshot storage errors | `STORAGE_BACKEND=local` |
| Frontend CORS | API allows `localhost:3000` and `127.0.0.1:3000` (dev only — prod uses an explicit allow-list via `CORS_ORIGINS`) |

---

## Tests & Linting

```powershell
# Backend
cd backend
.\.venv\Scripts\ruff check app tests
.\.venv\Scripts\ruff format --check app tests
.\.venv\Scripts\python -m pytest tests -q -m "not integration"

# Frontend
cd ..\frontend
npm run lint
npm test
npm run build
```
