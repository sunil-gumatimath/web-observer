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
#   NEXT_PUBLIC_INTERNAL_API_TOKEN=dev-internal-token  # dev/no-Clerk auth header
#   NEXT_PUBLIC_DEV_WORKSPACE_ID=  # optional: preselect a dev workspace
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
- Dashboard **Change-activity card** (`src/components/activity-card.tsx`): 7/14/30-day ranges, trend vs prior period, stacked bars by category; server data via `api.getChangeActivity` with UTC-safe client fallback (`src/lib/activity.ts`).
- Dashboard **Pause all / Resume all** bulk controls (confirm dialog, optimistic `enabled` flip).
- Monitor forms include a per-mode alert-thresholds editor (blank = alert on any change) plus a point-and-click selector picker (`selector-picker.tsx` + `lib/selector.ts`) for `list_items`.
- Monitor list has search, mode-filter, status-tabs, and sorting; monitor detail shows a before/after screenshot slider (`VisualDiff`) when screenshots exist.
- Alerts inbox items carry monitor brand marks (`BrandLogo` with domain-favicon fallback).
- Public share pages (`/share/[token]`) and team invites (`/invite/[token]`) are unauthenticated; in-app docs live at `/docs`.
- With Clerk keys set, you must **sign in**; API calls use Bearer JWTs only.
- **Failed to fetch** usually means the FastAPI process is not running on the configured port.
- Hydration warnings mentioning `rtrvr-ls` come from a browser extension (Retriever), not app state bugs.
- Backend start/docs: see repo root [README.md](../README.md) and [docs/local-dev.md](../docs/local-dev.md).
