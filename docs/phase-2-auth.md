<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Phase 2 Auth Setup (Clerk)

## Modes

| Mode | When | Frontend | Backend |
|------|------|----------|---------|
| **Dev** | No Clerk publishable key | `X-Internal-Token` | Accepts internal token |
| **Clerk** | Keys configured | `Authorization: Bearer <session JWT>` | Verifies JWT via JWKS; auto-provisions user + workspace |

With Clerk enabled, the UI **does not** fall back to the internal token (avoids wrong workspace / 404s). App routes are gated by `RequireAuth` (sign-in required).

## Clerk dashboard

1. Create an application at [clerk.com](https://clerk.com).  
2. Copy **Publishable key** and **Secret key**.  
3. Note Frontend API URL / issuer (e.g. `https://verb-noun-00.clerk.accounts.dev`).  
4. JWKS URL: `https://<same-host>/.well-known/jwks.json`.

## Frontend env (`frontend/.env.local`)

```env
# Port must match the running API
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
```

## Backend env (`backend/.env`)

```env
CLERK_JWKS_URL=https://verb-noun-00.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://verb-noun-00.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...   # optional; email enrichment
INTERNAL_API_TOKEN=dev-internal-token
```

Restart API after changing env.

## Flow

1. User signs in via Clerk (`/sign-in`).  
2. Client pages under `(app)/` wait for Clerk session (`RequireAuth`).  
3. Browser calls API with Bearer session token (`api.ts` + token bridge).  
4. FastAPI verifies RS256 JWT, upserts `users` by `clerk_user_id`, ensures a default workspace membership via `/api/v1/me`.  

## Timeouts (frontend)

- Clerk `getToken()` is capped (~5s) so the UI cannot hang forever.  
- API `fetch` aborts after ~20s (`Failed to fetch` / timeout if API is down).  

## Related

- [docs/clerk-setup.md](clerk-setup.md)  
- [docs/clerk-production.md](clerk-production.md)  
