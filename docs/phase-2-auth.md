# Phase 2 Auth Setup (Clerk)

## Modes

| Mode | When | Frontend | Backend |
|------|------|----------|---------|
| **Dev** | No Clerk publishable key | `X-Internal-Token` | Accepts internal token |
| **Clerk** | Keys configured | `Authorization: Bearer <session JWT>` | Verifies JWT via JWKS; auto-provisions user + workspace |

## Clerk dashboard

1. Create an application at [clerk.com](https://clerk.com).  
2. Copy **Publishable key** and **Secret key**.  
3. Note Frontend API URL / issuer (e.g. `https://verb-noun-00.clerk.accounts.dev`).  
4. JWKS URL: `https://<same-host>/.well-known/jwks.json`.

## Frontend env (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

## Backend env (root `.env`)

```env
CLERK_JWKS_URL=https://verb-noun-00.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://verb-noun-00.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...   # optional; email enrichment
```

Restart API after changing env.

## Flow

1. User signs in via Clerk (`/sign-in`).  
2. Middleware protects `/dashboard`, `/monitors`, etc.  
3. Browser calls API with Bearer session token.  
4. FastAPI verifies RS256 JWT, upserts `users` by `clerk_user_id`, ensures a default workspace membership.  
5. All workspace-scoped routes check `workspace_members`.

## Dev without Clerk

Leave Clerk keys empty. UI uses internal token; **Settings → Seed dev workspace** still works.

## Security notes

- Do not expose `INTERNAL_API_TOKEN` in production frontend builds.  
- In production, set Clerk keys and rotate/disable internal token usage from the browser.  
- Workspace membership is enforced on every monitor/run/change/snapshot route.  
