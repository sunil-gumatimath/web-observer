# Phase 3 — Reliability & JavaScript Rendering

## What shipped

| Capability | Implementation |
|------------|----------------|
| JS monitors | `monitors.js_required` → `browser_checks` queue |
| Playwright worker | `app/services/browser_fetch.py`, `worker-browser` service |
| Queue split | HTTP worker: `http_checks` + `notifications`; browser: `browser_checks` only |
| Ignore rules | `ignore_selectors` (CSS), `ignore_regexes` (text) on monitor |
| Domain rate limit | Redis `rate:{domain}:{minute}` |
| Domain concurrency | Redis `conc:{domain}` |
| Circuit breaker | Opens after N failures in window |
| Failure emails | After N consecutive failures (default 3) |
| Browser quota | `MAX_BROWSER_CHECKS_PER_DAY` per workspace (default 50) |

## Run

```bash
docker compose up --build
# Includes worker-browser (Playwright image, ~2GB RAM recommended)
```

Create a monitor with **JavaScript rendering required** in the UI, or:

```json
{ "js_required": true, "url": "https://spa.example.com", ... }
```

## Migration

```bash
cd backend
alembic upgrade head
# or rely on create_all for fresh local DBs (new columns on empty schema)
```

For existing DBs with data, run Alembic `002`.

## Ops notes

- Browser workers must not share capacity with API process.
- SSRF still applied to target URL and soft-checked on subresource routes.
- Media/fonts/stylesheets aborted in browser to reduce load.
