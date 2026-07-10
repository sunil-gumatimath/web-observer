# Clerk Production setup

Your app is linked as **monitor-the-web** (`app_3GJz6qgIFDXNyyMSm9ayJgXpZ6q`).

Right now only **Development** exists. Production is **not created yet**, so the UI shows **“Development mode”**.

## Why you still see Development mode

| Instance | Keys | Badge |
|----------|------|--------|
| Development | `pk_test_…` / `sk_test_…` | “Development mode” |
| Production | `pk_live_…` / `sk_live_…` | No “Development mode” (branding may still show on free plans) |

## Create Production (you do this in the browser)

1. Open [Clerk Dashboard](https://dashboard.clerk.com/)
2. Select app **monitor-the-web**
3. Open **Configure** / **Production** (or “Deploy to production”)
4. Complete the production checklist, typically:
   - Add your **production domain** (or use Clerk’s provisional host if offered)
   - For **local testing of prod keys**, add:
     - `http://localhost:3000`
     - `http://127.0.0.1:3000`
   - Finish DNS / SSL steps if using a custom domain
5. Wait until Production instance exists (status ready)

## Pull production keys into this project

After Production is created, from `frontend/`:

```powershell
cd frontend
clerk env pull --instance prod --app app_3GJz6qgIFDXNyyMSm9ayJgXpZ6q
```

Then wire backend JWKS/issuer:

```powershell
cd ..
node scripts\wire-clerk-backend.mjs
```

Restart frontend and API.

## Verify

```powershell
cd frontend
clerk doctor
```

You should see a **production** instance ID (not `production: null`).

Keys should look like:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...`
- `CLERK_SECRET_KEY=sk_live_...`

## Local vs production

| Use case | Use |
|----------|-----|
| Local coding / first tests | **Development** is fine |
| “Keep prod” / real users | **Production** keys only on the machine/server you deploy |

You can keep **dev keys** for local and **prod keys** only on a VPS later.  
If you want **only prod** even locally, use prod keys after Production is ready (and allow localhost in prod allowed origins).

## “Secured by Clerk” branding

Removing the Clerk badge usually requires a **paid Clerk plan**.  
Switching to Production removes **Development mode**, not always the branding.
