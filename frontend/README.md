# Web Observer — Frontend

Next.js (App Router) UI for Web Observer: monitors, alerts, settings, Clerk auth.

## Setup

```powershell
copy .env.example .env.local
# Edit:
#   NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002   # must match API port
#   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=...
#   CLERK_SECRET_KEY=...
npm install
```

## Dev server

```powershell
npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

## Notes

- With Clerk keys set, you must **sign in**; API calls use Bearer JWTs only.  
- **Failed to fetch** usually means the FastAPI process is not running on the configured port.  
- Hydration warnings mentioning `rtrvr-ls` come from a browser extension (Retriever), not app state bugs.  
- Backend start/docs: see repo root [README.md](../README.md) and [docs/local-dev.md](../docs/local-dev.md).  
