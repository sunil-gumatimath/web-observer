# Cloudflare free features wired into Web Observer

Web Observer uses a set of Cloudflare free-tier features. Every one of them is
optional, runs at $0 under the free quota, and can be switched off independently
by unsetting its env var.

| Feature | What it does here | Needs | Guide |
| ------- | ----------------- | ----- | ----- |
| **R2 Object Storage** | Stores raw HTML snapshots, normalized text, brand assets and screenshots (`STORAGE_BACKEND=s3`) — 10 GB free, zero egress | `S3_*` | [r2-setup.md](r2-setup.md) |
| **R2 screenshot bucket** | Puts screenshots in a *separate* public bucket so they can be served from a CDN domain instead of the API proxy | `S3_SCREENSHOT_BUCKET` + `NEXT_PUBLIC_SCREENSHOT_CDN_URL` | below |
| **Browser Rendering** | Edge Chromium used **only as a failover** when a local Playwright fetch fails | `CLOUDFLARE_BROWSER_URL` + `CLOUDFLARE_BROWSER_TOKEN` | below |
| **URL Scanner** | Backs the `security_scan` monitoring mode (verdict / categories / tech stack) | `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_URLSCANNER_TOKEN` | below |
| **Web Analytics** | Cookie-less, no-individual-tracking beacon on the Next.js UI | `NEXT_PUBLIC_CF_BEACON_TOKEN` | [web-analytics.md](web-analytics.md) |
| **Cloudflare Tunnel** | Exposes the local stack publicly without port-forwarding | connector token | below |
| **Workers** | `browser-failover` (edge browser) and `share-cache` (edge cache for share pages) | Wrangler deploy | below |

Account-level features work regardless of whether a domain is attached. The
zone-level ones (Tunnel hostnames, Cache Rules, WAF, Zero Trust Access) need a
zone you control.

---

## 1. R2 snapshots

Bucket `monitor-snapshots` with an Object-Read-&-Write token scoped to it,
credentials in `backend/.env` (`S3_*`). Details and the ping-test:
[docs/guides/r2-setup.md](r2-setup.md).

Create the token with a **1-year TTL** and rotate it before it expires — when
the token dies, snapshot writes start failing with `Unauthorized` and runs are
marked failed. On auth failure snapshots raise `StorageError` and never fall
back to local disk silently, so a dead token is loud rather than subtle.

Free quota: 10 GB-month storage, 1M Class-A + 10M Class-B ops/month, zero
egress.

## 2. R2 screenshot bucket (optional)

Snapshots are private, but screenshots are shown on public share pages and in
the alerts inbox. By default they are served through the API's asset proxy
(`GET /api/v1/public/assets/<key>`). To take the API out of the picture, put
screenshots in their own **public** bucket:

```env
# backend/.env
S3_SCREENSHOT_BUCKET=monitor-screenshots-public
```

```env
# frontend/.env.local
NEXT_PUBLIC_SCREENSHOT_CDN_URL=https://screenshots.example.com
```

The backend routes any object whose key starts with `screenshots/` to
`S3_SCREENSHOT_BUCKET` and everything else to `S3_BUCKET` — the choice is per
key, not per process (`backend/app/services/storage.py`). Bind the bucket's
custom domain to `NEXT_PUBLIC_SCREENSHOT_CDN_URL` and the frontend serves
screenshots straight from the CDN.

The API proxy stays in place as a fallback, so leaving `NEXT_PUBLIC_SCREENSHOT_CDN_URL`
unset is a valid configuration — you just pay the API hop.

## 3. Web Analytics

One env var, no code:

```env
# frontend/.env.local
NEXT_PUBLIC_CF_BEACON_TOKEN=<token>
```

Empty (the default) means the beacon never loads — zero network calls, nothing
tracked. Full setup and privacy notes: [web-analytics.md](web-analytics.md).

## 4. Cloudflare Browser Rendering failover

Local Playwright is **always the primary path**. The edge browser is only
consulted after a local browser fetch has actually failed, because the free
tier allows roughly 10 minutes of browser time per UTC day.

```
js_required monitor
      |
      v
local Playwright (primary)  --success--> done
      |
    failed
      |
      v
edge Worker (failover, once) --success--> done
      |
    failed
      |
      v
check fails
```

Deploy the Worker from `workers/browser-failover/`:

```bash
cd workers/browser-failover
npx wrangler deploy
# with the [browser] binding and a SHARED_TOKEN secret
npx wrangler secret put SHARED_TOKEN
```

Then point the backend at it:

```env
# backend/.env
CLOUDFLARE_BROWSER_URL=https://browser-failover.<subdomain>.workers.dev
CLOUDFLARE_BROWSER_TOKEN=<same value as the SHARED_TOKEN secret>
```

Notes:

- The Worker is a separate trust boundary. It returns raw HTML, so the backend
  re-applies SSRF validation to the *final* URL, the response size caps and
  bot-challenge detection to whatever comes back.
- The Worker is optional. With `CLOUDFLARE_BROWSER_URL` unset, a failed
  browser check simply fails.
- Some networks block `*.workers.dev` at the TCP/SNI level. If the failover
  fails fast with a connection error and local Playwright works fine, that is
  the cause — the failover engages on networks that allow it.
- Covered by `backend/tests/test_browser_failover.py`.

## 5. Cloudflare URL Scanner (`security_scan` mode)

```env
# backend/.env
CLOUDFLARE_ACCOUNT_ID=<account id>
CLOUDFLARE_URLSCANNER_TOKEN=<api token with URL Scanner permission>
```

Both are dashboard-only credentials (an OAuth session cannot mint them). With
a token, you can create a `security_scan` monitor that reports verdict,
category, tag, certificate, ASN and technology-stack changes on the URL. The
mode diffs a deterministic one-fact-per-line digest, so an alert says exactly
which fact moved.

Without a token the check **fails with a clear error** — it never silently
passes, so a misconfigured monitor is visible in the Logs page.

Keep the interval daily or slower: each check is a real edge scan.
Mode reference: [monitoring-modes.md](monitoring-modes.md).

## 6. Share-page edge cache Worker

`workers/share-cache/` is a Worker that caches `/share/` and `/_next/static/`
on the edge. It complements zone-level Cache Rules with explicit cache-key
scope and TTL trimming.

```bash
cd workers/share-cache
npx wrangler deploy
```

It runs standalone on `workers.dev` today. To put it in front of a real
hostname, set `CACHE_HOST` in `wrangler.toml` and add the route. Free-tier
Worker limits (100k req/day, 10 ms CPU) are far beyond what a read-only cache
interceptor needs.

## 7. Cloudflare Tunnel (optional)

`cloudflared` is installed (`winget install Cloudflare.cloudflared`).

1. Dashboard → **Zero Trust → Networks → Tunnels → Create tunnel** (name it
   `web-observer`).
2. Copy the connector token (the long `eyJ...` string, not the ID).
3. In the tunnel's **Public hostnames**, add:

   | Subdomain | Domain | Service |
   | --------- | ------ | ------- |
   | `app` | `your-domain.example` | `http://127.0.0.1:3000` |
   | `api` | `your-domain.example` | `http://127.0.0.1:8002` |

4. Then install the service locally:

```powershell
.\scripts\cloudflare-tunnel.ps1 -Token '<connector-token>'
# remove later:          .\scripts\cloudflare-tunnel.ps1 -Remove
# ephemeral one-off URL: .\scripts\cloudflare-tunnel.ps1 -Quick
```

The token is kept in `data/cloudflared-token.txt` (gitignored under `data/`).

### Wiring the public URL into the stack

Public UI served through the tunnel needs two env edits (in addition to
launching the stack):

```env
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=https://api.your-domain.example

# backend/.env
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://app.your-domain.example
```

`restart-stack.ps1` loads both files, so a restart after the edit is enough.

Security note: a tunnel makes the dev machine reachable from the internet.
The API keeps its normal auth (Clerk JWT / internal dev token) and
`APP_ENV=production` guards — treat the public hostnames as production and
drop the internal-token mode before sharing links.

---

## What is *not* wired

| Cloudflare feature | Status |
| ------------------ | ------ |
| Zero Trust Access | Account-level only; the API is deliberately **not** behind Access, because a login wall in front of every cross-origin call the UI makes would break the app. Gate the UI hostname only. |
| Cache Rules | Optional zone-level TTLs for `/share/*`, Next.js static assets and the screenshots CDN. The `share-cache` Worker is the code-level complement. |
| WAF / Bot Fight Mode | Optional zone-level rules. Note the backend's `/internal/*` routes are dev-only and should be blocked at the edge. |
| Turnstile | A widget exists on the account, but there is **no public form to protect** and no backend `siteverify` call. The fetcher only *detects* Turnstile challenge markers. Empty keys = feature off. |
| D1, Queues, Cron + Hyperdrive, Pages | Not used. |

## Related

- [docs/guides/r2-setup.md](r2-setup.md) — R2 bucket + token + ping test
- [docs/guides/web-analytics.md](web-analytics.md) — Web Analytics beacon
- [docs/guides/monitoring-modes.md](monitoring-modes.md) — the `security_scan` mode
- [docs/architecture.md](../architecture.md) — where the edge tier sits in the system
