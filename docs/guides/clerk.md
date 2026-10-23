<p align="center">
  <img src="../../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Clerk setup

Two stages: **development** (the default, fine for local work and first
tests) and **production** (a separate Clerk instance with `pk_live_` keys).
For how the API accepts each credential, see
[docs/auth-modes.md](../auth-modes.md).

The app is linked as **Web Observer** (`app_3GJz6qgIFDXNyyMSm9ayJgXpZ6q`).

---

## Development setup

Example (as of 2026-09): linked app **Web Observer** (`app_3GJz6qgIFDXNyyMSm9ayJgXpZ6q`)
Frontend API host: `suited-emu-70.clerk.accounts.dev` (development)

### What was configured

| Layer | What |
| ------- | ------ |
| **Frontend** | `@clerk/nextjs`, `ClerkProvider` in layout, `clerkMiddleware` in `frontend/src/proxy.ts` (Next.js 16's rename of `middleware.ts`), sign-in/up pages |
| **frontend/.env.local** | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` (via `clerk env pull`) |
| **Backend .env** | `CLERK_JWKS_URL`, `CLERK_ISSUER`, `CLERK_SECRET_KEY` for FastAPI JWT verify (set in `backend/.env`) |
| **UI** | Sign in / Sign up / UserButton in nav |

### Get the keys

1. Create an application at [clerk.com](https://clerk.com).
2. Copy **Publishable key** and **Secret key**.
3. Note Frontend API URL / issuer (e.g. `https://verb-noun-00.clerk.accounts.dev`).
4. JWKS URL: `https://<same-host>/.well-known/jwks.json`.

`frontend/.env.local`:

```env
# Port must match the running API
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
```

`backend/.env`:

```env
CLERK_JWKS_URL=https://verb-noun-00.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://verb-noun-00.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...   # optional; email enrichment
INTERNAL_API_TOKEN=dev-internal-token
```

Restart the API after changing env.

### Run with Clerk

1. Start Postgres + Redis + API + worker (see [docs/local-dev.md](../local-dev.md))
2. Restart the API so it loads `backend/.env` Clerk vars
3. Frontend:

```powershell
cd frontend
npm run dev
```

4. Open <http://127.0.0.1:3000> → **Sign up** → create your first user
5. Dashboard should load; API calls use the Bearer session JWT

### Re-sync keys later

```powershell
cd frontend
clerk env pull --app app_3GJz6qgIFDXNyyMSm9ayJgXpZ6q
cd ..
# Update CLERK_ISSUER and CLERK_JWKS_URL in the root .env to match the frontend Clerk instance.
```

### Dashboard

<https://dashboard.clerk.com/>

If you see **Configure your application**, click it and finish any checklist items (allowed origins, etc.).

Add `http://localhost:3000` and `http://127.0.0.1:3000` to allowed origins if auth redirects fail.

---

## Production setup

Right now only **Development** exists. Production is **not created yet**, so the UI shows **"Development mode"**.

### Why you still see Development mode

| Instance | Keys | Badge |
| ---------- | ------ | -------- |
| Development | `pk_test_…` / `sk_test_…` | "Development mode" |
| Production | `pk_live_…` / `sk_live_…` | No "Development mode" (branding may still show on free plans) |

### Create Production (you do this in the browser)

1. Open [Clerk Dashboard](https://dashboard.clerk.com/)
2. Select app **Web Observer**
3. Open **Configure** / **Production** (or "Deploy to production")
4. Complete the production checklist, typically:
   - Add your **production domain** (or use Clerk's provisional host if offered)
   - For **local testing of prod keys**, add:
     - `http://localhost:3000`
     - `http://127.0.0.1:3000`
   - Finish DNS / SSL steps if using a custom domain
5. Wait until Production instance exists (status ready)

### Pull production keys into this project

After Production is created, from `frontend/`:

```powershell
cd frontend
clerk env pull --instance prod --app app_3GJz6qgIFDXNyyMSm9ayJgXpZ6q
```

Then wire backend JWKS/issuer:

```powershell
cd ..
# Update CLERK_ISSUER and CLERK_JWKS_URL in the root .env to match the frontend Clerk instance.
```

Restart frontend and API.

### Verify

```powershell
cd frontend
clerk doctor
```

You should see a **production** instance ID (not `production: null`).

Keys should look like:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...`
- `CLERK_SECRET_KEY=sk_live_...`

### Local vs production

| Use case | Use |
|----------|-----|
| Local coding / first tests | **Development** is fine |
| "Keep prod" / real users | **Production** keys only on the machine/server you deploy |

You can keep **dev keys** for local use and **prod keys** only in the environment you use for real users.
If you want **only prod** even locally, use prod keys after Production is ready (and allow localhost in prod allowed origins).

### "Secured by Clerk" branding

Removing the Clerk badge usually requires a **paid Clerk plan**.
Switching to Production removes **Development mode**, not always the branding.

---

## Related

- [docs/auth-modes.md](../auth-modes.md) — the three credentials the API accepts
- [docs/local-dev.md](../local-dev.md) — running the stack locally
- [docs/integrations/n8n-zapier.md](../integrations/n8n-zapier.md) — API keys and webhooks
