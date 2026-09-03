<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Web Observer — Frontend

Next.js (App Router) UI for Web Observer: monitors, alerts, settings, Clerk auth.

## Setup

```powershell
copy .env.example .env.local
# Edit:
#   NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002   # must match API port
#   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=...
#   CLERK_SECRET_KEY=...
bun install # or npm install
```

## Dev server

```powershell
bun run dev --port 3000 # or npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

Tip: `powershell -File .\scripts\restart-stack.ps1` (from the repo root) launches the full stack — API :8002, both workers, scheduler, and this frontend — in hidden windows with logs in `data\logs`.

## Notes

- Command palette: `Ctrl+K` / `Cmd+K` for monitor search and quick actions.
- Toasts surface success/error feedback for alert and settings actions.
- Dashboard onboarding checklist guides first monitor → run → alert setup.
- Monitor forms include a per-mode alert-thresholds editor (blank = alert on any change).
- Monitor detail shows a before/after screenshot slider (`VisualDiff`) when screenshots exist.
- With Clerk keys set, you must **sign in**; API calls use Bearer JWTs only.
- **Failed to fetch** usually means the FastAPI process is not running on the configured port.
- Hydration warnings mentioning `rtrvr-ls` come from a browser extension (Retriever), not app state bugs.
- Backend start/docs: see repo root [README.md](../README.md) and [docs/local-dev.md](../docs/local-dev.md).
