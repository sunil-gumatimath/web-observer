<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Phase 3 — Reliability & JavaScript Rendering

## What shipped

| Capability | Implementation |
|------------|----------------|
| JS monitors | `monitors.js_required` → `browser_checks` queue |
| Opt-in screenshots | `monitors.screenshots_enabled` → full-page screenshot attached to checks/alerts (any mode); no separate visual mode exists |
| Playwright fetch | `app/services/browser_fetch.py` |
| Playwright screenshot | `app/services/visual.py` |
| Isolated jobs | `app/services/playwright_job.py` (subprocess; avoids Windows EBADF) |
| Queue split | HTTP worker: `http_checks` + `notifications`; browser: `browser_checks` only |
| Ignore rules | `ignore_selectors` (CSS), `ignore_regexes` (text) on monitor |
| Domain rate limit | Redis `rate:{domain}:{minute}` |
| Domain concurrency | Redis `conc:{domain}` |
| Circuit breaker | Opens after N failures in window |
| Failure emails | After N consecutive failures (default 3) |
| Browser quota | `MAX_BROWSER_CHECKS_PER_DAY` per workspace (default 50) |

## Run (no Docker)

```powershell
# HTTP worker
.\.venv\Scripts\dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2

# Browser worker — Windows: always --threads 1
.\.venv\Scripts\dramatiq app.workers --queues browser_checks --processes 1 --threads 1

# Once
.\.venv\Scripts\python -m playwright install chromium
```

Or: `powershell -File .\scripts\restart-stack.ps1`

Docker (optional):

```bash
docker compose up --build
# Includes worker-browser if defined in compose
```

Create a monitor with **JavaScript rendering required** or **Visual** mode in the UI.

## Migration

```bash
cd backend
alembic upgrade head
# Alembic is required in production/staging; create_all only runs when APP_ENV in (development, test, testing) — see backend/app/main.py.
```

## Ops notes

- Browser workers must not share capacity with multi-thread HTTP workers.  
- Sync Playwright is **not thread-safe** on Windows → `--processes 1 --threads 1`.  
- Capture runs in a **child process** so Dramatiq pipe handles cannot break Chromium.  
- Typical Windows failure without isolation: `Screenshot failed: [Errno 9] Bad file descriptor`.  
- SSRF applied to target URL; soft-checked on browser subresources.  
- Media/fonts/stylesheets aborted in JS fetch path to reduce load.  
