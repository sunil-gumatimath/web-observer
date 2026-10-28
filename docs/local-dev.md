<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Local development & operations

You need:

1. **Python 3.11+** (3.12 fine)
2. **Node.js 20+**
3. **PostgreSQL** — **Neon** cloud URL or local install
4. **Redis** — local install / WSL / Memurai

Snapshots go to `./data/snapshots`.

Part 1 (sections 1–7) is the runbook: how to get the stack up and what each
process is. Part 2 (sections 8–15) is the operational reference: environments,
release basics, service targets, Workers, secrets, retention, observability,
and the current state of hosting.

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

**Auto-start.** `scripts/restart-stack.ps1` probes `127.0.0.1:6379` before launching anything. If Redis is not answering it runs `sudo -n systemctl start redis-server` inside WSL2 and re-probes for ~10 s. On success it also leaves a **detached hold-open session** (`wsl.exe -d Ubuntu-26.04 --exec sleep infinity`) so the VM — and Windows' localhost forwarding — cannot idle out while the stack runs; the session exits with the machine, and `wsl --shutdown` clears it. `sudo -n` means passwordless sudo must already be configured, and the distro name is hard-coded: if yours is not `Ubuntu-26.04`, edit that line in `scripts/restart-stack.ps1` or start Redis yourself. A failed preflight is not fatal — workers and the rate limiter degrade rather than block.

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

Preferred on Windows — one command launches all 5 processes hidden (API :8002, HTTP+notifications worker, browser worker, scheduler, frontend :3000). It also preflights Redis and auto-starts it inside WSL2 when needed (see [§1](#redis)):

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
| <http://127.0.0.1:8002/metrics> | Prometheus metrics |

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
# Optional: Cloudflare Web Analytics beacon (empty = beacon never loads)
# NEXT_PUBLIC_CF_BEACON_TOKEN=
# Optional: serve screenshots from a public R2 bucket CDN instead of the API proxy
# NEXT_PUBLIC_SCREENSHOT_CDN_URL=https://screenshots.example.com
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
| Runs export | `GET /api/v1/workspaces/{id}/export/runs?format=csv\|json` — CSV/JSON export honouring the same filters as the logs list (20k-run cap, `runs.exported` audit entry) |
| Monitor SSE stream | `GET /api/v1/workspaces/{id}/monitors/{monitor_id}/events` — run-status/change events; 1-hour lifetime, 15s heartbeat, Redis ORM-wakeup hints from `app/services/live_events.py` (candidates: pipeline, workers, scheduler, reaper). Without Redis the publisher circuit-breaks and the stream falls back to a 1.5s poll tick |
| Bulk pause / resume | `POST /api/v1/workspaces/{id}/monitors/pause-all`, `.../resume-all` (resume re-schedules `next_run_at`) |
| Selector preview | `POST /api/v1/workspaces/{id}/monitors/selector-preview` — sanitized HTML for the point-and-click picker |
| Brand info | `POST /api/v1/workspaces/{id}/monitors/brand-info` — logo/title/description auto-fill |
| Change Q&A | `POST /api/v1/workspaces/{id}/changes/{change_id}/ask-ai` — ask a question about one change (5/minute) |
| Status badge | `GET /api/v1/workspaces/{id}/monitors/{monitor_id}/badge.svg` — public SVG badge, no auth |
| Value history | `GET /api/v1/workspaces/{id}/monitors/{monitor_id}/value-history` — chartable series for `product_price` / `json_field` |
| Mark all read | `POST /api/v1/workspaces/{id}/alerts/read-all` |
| Snapshot download | `GET /api/v1/workspaces/{id}/snapshots/{snapshot_id}` |
| Prometheus metrics | `GET /metrics` — monitors total, runs/changes in 24h, outbox and webhook backlog (30/minute) |

Fetch behavior worth knowing while debugging:

- The SSRF-pinned fetcher tries **every** validated IP in turn — one dead CDN PoP won't fail a check; only connect-level errors trigger failover (`backend/app/services/fetcher.py:_pinned_get`).
- `readme` monitors hit the GitHub API first (`ref`-pinned to the parsed `/tree/<branch>` branch when there is one, default branch otherwise), then fall back to raw probes bounded by a wall-clock budget (fits inside the worker's 120s time limit).
- LLM summaries fail over across `LLM_FALLBACK_MODELS`; `none` disables failover. The catalog default is the model list of the provider that `LLM_API_BASE` points at (see `backend/app/services/model_catalog.py`).
- The Kilo catalog is **probe-ranked, not copied from the provider list**: every free model was run with the app's real prompt at the 200- and 800-token caps, and each entry's `note` records what happened plus the `verified_at` cap it needs (200 = fits the default cap, 800 = needs the larger one, absent = failed). The list is refreshed by re-running those probes and re-ranking — a model that is free today can 429, empty out, or reject structured output tomorrow, so treat the notes as dated evidence (currently 2026-10-28). Only `poolside/laguna-s-2.1:free` is verified at the default cap.
- `js_required` monitors fall back to the **Cloudflare Browser Rendering Worker** when the local Playwright fetch fails (`CLOUDFLARE_BROWSER_URL` + `CLOUDFLARE_BROWSER_TOKEN`). Local stays primary so the free ~10 min/day edge-browser quota is preserved. Covered by `backend/tests/test_browser_failover.py`.
- `security_scan` monitors run on Cloudflare's edge via the URL Scanner (`CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_URLSCANNER_TOKEN`). With no token the check fails with a clear error instead of silently passing.

Optional env (defaults work locally):

```env
LLM_API_KEY=            # empty => heuristic summaries only
LLM_API_BASE=https://api.kilo.ai/api/gateway
LLM_MODEL=poolside/laguna-s-2.1:free
LLM_FALLBACK_MODELS=    # empty => catalog default for the active provider; "none" => primary only

STORAGE_BACKEND=local   # set to s3 + endpoint/keys for GCS/R2-compatible storage

# Screenshots in their own public bucket (R2 + CDN custom domain)
S3_SCREENSHOT_BUCKET=
```

Every supported variable is listed with its default in [`.env.example`](../.env.example).

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

## 8. Stack topology & environments

What runs natively, one row per service:

| Service | Native |
| --------- | --------------------------------------- |
| `postgres` | Neon URL or local Postgres (`DATABASE_URL`) |
| `redis` | `localhost:6379` (WSL / Memurai) |
| `api` | `uvicorn app.main:app` (port 8002) |
| `scheduler` | `python -m app.scheduler` |
| `worker` | `dramatiq app.workers` (http_checks + notifications) |
| `worker-browser` | `dramatiq app.workers --queues browser_checks` (`--threads 1`) |
| `web` | `next dev` (frontend, port 3000) |

Environments:

| Env | Purpose |
| ----- | --------- |
| local | Dev |
| test | CI automated |

Staging/production are not configured (hosting config removed).

## 9. Release basics

- Migrations via Alembic (`alembic upgrade head`) — the schema's only source of truth
  (head revision: `015_change_run_set_null`)
- Health/readiness probes (`/health`, `/ready`)
- Prometheus metrics (`/metrics`, rate limited to 30/minute): monitors total,
  runs and changes in the last 24h, outbox and webhook backlog
- Worker concurrency via env

## 10. Service targets

The operating targets this service is held to. These are the private-beta
acceptance thresholds, not aspirations — a regression against any of them is
a defect.

| Metric | Target |
| -------- | -------- |
| Successful eligible checks | ≥ 99% |
| Lightweight checks within 15s | ≥ 95% |
| Checks start within 5 min of schedule | ≥ 99% |
| Duplicate notifications | < 1 / 10,000 deliveries |
| Alerts rated useful | ≥ 90% |
| Cross-workspace incidents | 0 |
| Successful SSRF to blocked targets | 0 |
| 4-week workspace retention | ≥ 30% |

### Product and cost metrics to track

- Active monitors / workspaces
- Monitored domains
- Checks per day
- Changes detected
- Alert CTR / diff views
- Schedule → notification latency
- Monitors paused/deleted after noise
- Noise feedback rate
- WAU/MAU retention
- Trial → paid (when billing exists)
- Cost / 1,000 HTTP checks · Cost / 1,000 browser checks · Storage $ / workspace
  · Notification $ / workspace · AI $ / summary · Infra $ / active monitor

Per-workspace quota **values** (max monitors, checks/day, browser checks/day,
response size, storage, deliveries/day, per-domain rate and concurrency, API
rate limit) are not repeated here — they are configuration, and
[`.env.example`](../.env.example) is the source of truth for their defaults.
The security rationale behind the limits lives in the
[threat model](security/threat-model.md).

## 11. Cloudflare Workers

Two Workers live in `workers/` and are deployed separately from the app:

| Worker | Purpose | Source |
| ------ | ------- | ------ |
| `browser-failover` | Edge Chromium used **only** as a failover for `js_required` fetches, after a local Playwright fetch has already failed. Free quota is ~10 min of browser time per UTC day, so local stays primary. | `workers/browser-failover/` |
| `share-cache` | Edge cache for public share pages and Next.js static assets (`/share/`, `/_next/static/`). Deployed standalone; attach routes when a public hostname exists. | `workers/share-cache/` |

Neither Worker is required for the stack to run. If `CLOUDFLARE_BROWSER_URL` is
unset, the failover is simply off and a failed browser check fails.

## 12. Secrets

| Secret | Used by |
| -------- | --------- |
| `DATABASE_URL` | api, scheduler, workers |
| `REDIS_URL` | api, scheduler, workers |
| `CLERK_*` | api, web |
| `S3_*` / `R2_*` | workers, api (optional object storage) |
| `RESEND_API_KEY` | notification worker |
| `SECRET_KEY` | api (encryption key + API-key HMAC — pin in production) |
| `INTERNAL_API_TOKEN` | admin |
| `LLM_API_KEY` | api + workers (AI summaries, triage) |
| `CLOUDFLARE_BROWSER_TOKEN` | workers (Browser Rendering failover) |
| `CLOUDFLARE_URLSCANNER_TOKEN` | workers (`security_scan` mode) |

## 13. Snapshot retention (matches `backend/app/services/retention.py`)

| Data | Default |
| ---- | ------- |
| Raw HTML + normalized-text objects | 30 days (`SNAPSHOT_RETENTION_DAYS`, purged with the snapshot) |
| Screenshot objects | 30 days (same window, deleted with the snapshot that produced them) |
| Snapshots (DB rows) | 30 days (same window) — **but** a snapshot still referenced by a change event is kept |
| Monitor runs | 90 days (`RUN_RETENTION_DAYS`) |
| Change events | **Never purged** by `retention_job`. Since migration `015` a change event's `run_id` is `SET NULL`, so run cleanup no longer destroys the alerts inbox, and a snapshot referenced as a change's `new_snapshot` is explicitly retained. |
| Outbox / deliveries | Not purged by `retention_job` |

User delete monitor → delete associated history + enqueue object deletes.

> Retention is deliberately biased towards keeping the inbox: a change event
> without its snapshot is still a usable record (title, impact, summary, diff
> summary), while losing a change event loses user-visible history.
> See `backend/app/services/retention.py` and
> `backend/tests/test_retention_events.py`.

## 14. Observability correlation IDs

Always log these IDs — and never log page bodies, credentials, or sensitive
headers:

- `workspace_id`
- `monitor_id`
- `run_id`
- `change_event_id`
- `delivery_id`

## 15. Production / hosting

- No deploy target or pipeline is configured (staging/production undecided — see roadmap Phase 10).
- Enterprise deploy is undecided — see roadmap Phase 10.
- Cloud hosting configuration (Cloud Run, Cloud Build, Render, Vercel) has not been set up — see the last section of this doc.

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
| `security_scan` monitor fails immediately | No `CLOUDFLARE_URLSCANNER_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` on the server — the mode errors clearly rather than silently passing. Both are dashboard-only tokens. |
| Browser check fails but plain HTTP works | The Cloudflare Browser Rendering failover is a *fallback*, not a replacement: it only engages after a local Playwright fetch has already failed. Check `CLOUDFLARE_BROWSER_URL` / `CLOUDFLARE_BROWSER_TOKEN`, and that the edge hostname is reachable (some ISPs block `*.workers.dev`). |
| Screenshots 404 on the monitor page | The screenshot is still in the browser queue — the image is only stored once the change is captured. The visual diff slider retries with a cache-buster. Also check `S3_SCREENSHOT_BUCKET` vs `NEXT_PUBLIC_SCREENSHOT_CDN_URL` agree. |
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
