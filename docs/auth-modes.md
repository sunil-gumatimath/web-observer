<p align="center">
  <img src="../../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Auth modes

The API accepts **three** credentials. The frontend uses the first two
depending on whether Clerk is configured; the third is for scripts and
integrations.

| Mode | Credential | Header | Who uses it |
|------|-----------|--------|-------------|
| **Dev (internal token)** | `INTERNAL_API_TOKEN` | `X-Internal-Token: <token>` | Local development without Clerk. Grants **owner-equivalent** access. |
| **Clerk** | Clerk session JWT | `Authorization: Bearer <jwt>` | The web UI when Clerk keys are configured. |
| **API key** | `mtw_...` | `Authorization: Bearer mtw_...` | Scripts, n8n, Zapier, CI. Scoped to one workspace. |

The frontend picks its mode automatically:

| Mode | When | Frontend | Backend |
|------|------|----------|---------|
| **Dev** | No Clerk publishable key | `X-Internal-Token` | Accepts internal token |
| **Clerk** | Keys configured | `Authorization: Bearer <session JWT>` | Verifies JWT via JWKS; auto-provisions user + workspace |

With Clerk enabled, the UI **does not** fall back to the internal token (avoids wrong workspace / 404s). App routes are gated by `RequireAuth` (sign-in required).

> `NEXT_PUBLIC_INTERNAL_API_TOKEN` is bundled into the browser, so it is
> visible to anyone who can load the page. It is a **development-only** shared
> secret. In a production build the frontend forces Clerk auth and the token
> is not used. Never point a public deployment at the internal-token mode.

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

## Flow (Clerk)

1. User signs in via Clerk (`/sign-in`).  
2. Client pages under `(app)/` wait for Clerk session (`RequireAuth`).  
3. Browser calls API with Bearer session token (`api.ts` + token bridge).  
4. FastAPI verifies RS256 JWT, upserts `users` by `clerk_user_id`, ensures a default workspace membership via `/api/v1/me`.  

## Flow (API key)

1. Create a key in **Settings → API keys**. The raw `mtw_...` value is shown
   **once**; only a hash is stored.
2. Send it as `Authorization: Bearer mtw_...` on every request.
3. Revoke it from the same panel — revocation is immediate.

Keys are hashed with an HKDF-derived secret and a `v2$` scheme prefix; the
legacy `v1$` and plain-text schemes are still verified, so old keys keep
working and no migration is needed. See `backend/app/services/api_keys.py`.

## Rate limiting

Every route is rate limited (default 60/min) against the **verified**
principal — a Clerk user, an API key, the internal token, or the caller's IP
when unauthenticated. Counter storage is Redis-backed and **fails open** to
per-process memory if Redis is unreachable, so a Redis outage cannot turn
traffic into 500s. See `backend/app/rate_limit.py`.

## Timeouts (frontend)

- Clerk `getToken()` is capped at 5s so the UI cannot hang forever.  
- API `fetch` aborts after 30s (`Failed to fetch` / timeout if API is down).  

## Related

- [docs/guides/clerk.md](guides/clerk.md) — dev setup and production hardening  
- [docs/integrations/n8n-zapier.md](integrations/n8n-zapier.md) — API keys and webhooks
