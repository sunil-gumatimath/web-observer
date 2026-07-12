# Local development **without Docker**

You only need:

1. **Python 3.12+**
2. **Node.js 20+**
3. **PostgreSQL** (local install)
4. **Redis** (local install)

No Docker, no MinIO required. Snapshots go to `./data/snapshots`.

---

## 1. Install Postgres & Redis (Windows)

**Postgres**

- Install from https://www.postgresql.org/download/windows/
- Create user/db (pgAdmin or `psql`):

```sql
CREATE USER monitor WITH PASSWORD 'monitor';
CREATE DATABASE web_observer OWNER monitor;
```

**Redis**

- Option A: [Memurai](https://www.memurai.com/) (Redis-compatible on Windows)
- Option B: WSL2 `sudo apt install redis-server && redis-server`
- Option C: Redis Windows port / Scoop: `scoop install redis`

Default: `redis://localhost:6379/0`

---

## 2. Backend env

From repo root:

```powershell
copy .env.example .env
# .env already points at localhost + STORAGE_BACKEND=local
```

---

## 3. Backend venv + deps

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional (only if you use JS/visual monitors):

```powershell
playwright install chromium
```

---

## 4. Start backend processes (4 terminals)

All from `backend` with venv activated, and env loaded from parent `.env`:

```powershell
# Terminal A — API
cd backend
$env:DATABASE_URL="postgresql+psycopg://monitor:monitor@localhost:5432/web_observer"
$env:REDIS_URL="redis://localhost:6379/0"
$env:STORAGE_BACKEND="local"
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

```powershell
# Terminal B — HTTP + notification workers
cd backend
$env:DATABASE_URL="postgresql+psycopg://monitor:monitor@localhost:5432/web_observer"
$env:REDIS_URL="redis://localhost:6379/0"
$env:STORAGE_BACKEND="local"
.\.venv\Scripts\dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2
```

```powershell
# Terminal C — Scheduler
cd backend
$env:DATABASE_URL="postgresql+psycopg://monitor:monitor@localhost:5432/web_observer"
$env:REDIS_URL="redis://localhost:6379/0"
.\.venv\Scripts\python -m app.scheduler
```

Optional browser worker (JS/visual):

```powershell
# Terminal D
cd backend
$env:DATABASE_URL="postgresql+psycopg://monitor:monitor@localhost:5432/web_observer"
$env:REDIS_URL="redis://localhost:6379/0"
.\.venv\Scripts\dramatiq app.workers --queues browser_checks --processes 1 --threads 1
```

Or use the helper script:

```powershell
# from repo root (starts API only in one window; open others as needed)
.\scripts\run-local.ps1
```

API: http://localhost:8000/docs  
Health: http://localhost:8000/health  

Tables are created automatically on API startup (`create_all`).

---

## 5. Frontend

```powershell
cd frontend
copy .env.example .env.local
# NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
# NEXT_PUBLIC_INTERNAL_API_TOKEN=dev-internal-token
npm install
npm run dev
```

UI: http://localhost:3000  

1. Open **Settings → Seed dev workspace** (or Ensure workspace)  
2. Create a monitor  
3. **Run now**

---

## 6. Minimum set for “does it work?”

| Process | Required? |
|---------|-----------|
| Postgres | Yes |
| Redis | Yes (queue + rate limits) |
| API (`uvicorn`) | Yes |
| Worker (`dramatiq` http+notifications) | Yes for checks/alerts |
| Scheduler | Yes for scheduled checks (manual run works without it) |
| Browser worker | Only for `js_required` / visual |
| MinIO / Docker | **No** |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Can't connect to DB | Check Postgres running; URL uses `localhost` not `postgres` |
| Dramatiq / Redis errors | Start Redis; `REDIS_URL=redis://localhost:6379/0` |
| Snapshot storage errors | `STORAGE_BACKEND=local` (default) |
| Domain rate limit in tests | Redis must be up for live checks |
| Frontend CORS | API allows `localhost:3000` already |

---

## Unit tests (no Postgres/Redis needed for most)

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q -m "not integration"
```
