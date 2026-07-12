# Clerk setup (this project)

Linked app: **Web Observer** (`app_3GJz6qgIFDXNyyMSm9ayJgXpZ6q`)  
Frontend API host: `suited-emu-70.clerk.accounts.dev` (development)

## What was configured

| Layer | What |
|-------|------|
| **Frontend** | `@clerk/nextjs`, `ClerkProvider` in layout, middleware protect, sign-in/up pages |
| **frontend/.env.local** | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` (via `clerk env pull`) |
| **Root .env** | `CLERK_JWKS_URL`, `CLERK_ISSUER`, `CLERK_SECRET_KEY` for FastAPI JWT verify |
| **UI** | Sign in / Sign up / UserButton in nav |

## Run with Clerk

1. Start Postgres + Redis + API + worker (see `docs/local-dev.md`)  
2. Restart API so it loads root `.env` Clerk vars  
3. Frontend:

```powershell
cd frontend
npm run dev
```

4. Open http://localhost:3000 → **Sign up** → create your first user  
5. Dashboard should load; API calls use Bearer session JWT  

## Re-sync keys later

```powershell
cd frontend
clerk env pull --app app_3GJz6qgIFDXNyyMSm9ayJgXpZ6q
cd ..
node scripts/wire-clerk-backend.mjs
```

## Dashboard

https://dashboard.clerk.com/

If you see **Configure your application**, click it and finish any checklist items (allowed origins, etc.).

Add `http://localhost:3000` to allowed origins if auth redirects fail.
