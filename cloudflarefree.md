# Cloudflare free tier for Web Observer — phase plan

Every Cloudflare feature this project can use at **$0/mo**, broken into phases.
Each phase is independently shippable: do them top to bottom, stop whenever the
free quota no longer fits, and roll back any phase without touching the others.

> Quotas verified against Cloudflare docs on **2026-10-21**. Cloudflare changes
> free-tier numbers occasionally — re-check the linked doc per phase if a number
> looks off. AI products (Workers AI, AI Gateway, Vectorize) are intentionally
> excluded everywhere in this doc.

**Account / zone** (same as `docs/guides/cloudflare-free-features.md`):

| Thing | Value |
| --- | --- |
| Account | `Clevertedz@gmail.com` — Account ID `90917fcff9681d8b8da94ee10b0ac7fb` |
| Zone | `sunilted.qzz.io` |
| Public hostnames (tunnel) | `app.sunilted.qzz.io` → `127.0.0.1:3000` · `api.sunilted.qzz.io` → `127.0.0.1:8002` |

**Status legend:** ✅ live · 🔑 one credential/config away · 🚧 needs code · 📋 planned / not started

| Phase | Feature | Status | Effort |
| ----- | -------- | ------ | ------ |
| 0 | R2 snapshots + Tunnel + Web Analytics | ✅ live (connector running detached; service install still pending) | done |
| 1 | Zero Trust Access in front of the tunnel | ✅ live (UI only) | done via API 2026-10-21 |
| 2 | Cache Rules (`/share/*` + static assets + screenshots CDN) | ✅ live (3 rules) | done via API 2026-10-21 |
| 3 | R2 lifecycle rules + public screenshots bucket | ✅ live (bucket wiring; R2 token scope pending) | done via API + code |
| 4 | WAF custom rules + rate limiting + Bot Fight Mode | ✅ live | done via API 2026-10-21 |
| 5 | Turnstile on public surfaces | 🔑 keys ready, feature off (no public form to protect) | widget + keys done via API 2026-10-21 |
| 6 | Worker edge cache (+ KV) for share pages | ✅ deployed standalone; wire route when a public host exists | small Worker + route |
| 7 | Browser Rendering failover for `js_required` | ✅ live via API (dormant on this ISP — workers.dev blocked) | Worker + failover ladder wired |
| 8 | Email Routing — "email a URL to check it" | 🚧 | Email Worker |
| 9 | Radar API + URL Scanner monitor mode | ✅ backend built; 🔑 awaiting user API token | backend feature |
| 10 | Optional/deprioritized (D1, Queues, Cron+Hyperdrive, Pages, Workers Logs) | 📋 | — |

### Executed 2026-10-21 (Phases 1, 2, 3.1, 4, 7 — via API, no dashboard clicks)

| What | Resource ID / value |
| ---- | ------------------- |
| Zero Trust org | team `web-observer` — auth domain `web-observer.cloudflareaccess.com` |
| Access app | `Web Observer UI` — `app.sunilted.qzz.io`, session 24h, app id `f4a967d6-3bbb-42df-b4ce-7ebd2f9e6f63`, aud `3b78f0119e1c…` |
| Access policy | `Just me` — Allow, email include, id `b24a990e-8e92-41c2-8d02-0f2d4bce899c` |
| 3.1 R2 lifecycle | `expire-snapshots-30d` — prefix `workspaces/`, delete after 30 days (`maxAge 2592000`); default multipart-abort rule preserved |
| 2 Cache ruleset | `6ec3e46fca3a41529f79b29712ea6b4e` (v2) — `share-pages` (edge TTL 300s), `next-static` (edge TTL 86400s), `screenshots-cdn` (edge TTL 86400s) |
| 4.1 WAF ruleset | `a22b986e58594aab836b7315cca77a63` — block `/.env`+`/.git` probes · block `/internal` from edge (whole zone, incl. only-known-IP variance replaced with hard block) |
| 4.2 Rate limit | `378a81f1d0cf4ffaab2aeb27cd84c294` — 100 req/10s per IP (`cf.colo.id`+`ip.src`), **block 10s** (free-plan cap — not 1 min) for `/api` paths |
| 4.3 Bot Fight Mode | ON (`fight_mode: true`, `enable_js: true` — API requires EnableJS to be on before Fight Mode) |
| 0.3 Web Analytics | site `app.sunilted.qzz.io` created via RUM API; beacon token set in `frontend/.env.local` |
| 3.2 Screenshots CDN | bucket `monitor-screenshots-public` + custom domain `screenshots.sunilted.qzz.io` (DNS auto) + storage key-prefix routing + `screenshotUrl()` frontend helper |
| Tunnel (Phase 0.2) | `web-observer-tunnel` `764ebb31-9a17-43eb-a966-dc4cb90e2ce7` — ingress + DNS via API, connector token fetched via API, connector running (status **healthy**, 4 conns via `bom`/`maa` colos); saved to `data/cloudflared-token.txt` (token file + service removed in the local-only rollback below) |
| 7 Browser Rendering failover (2026-10-21, via API) | Worker `browser-failover` uploaded with the `[browser]` BROWSER binding + `SHARED_TOKEN` secret → `https://browser-failover.clevertedz.workers.dev` (account workers.dev subdomain `clevertedz` created). Worker source lives in `workers/browser-failover/`. Backend failover ladder: local Playwright stays **primary** (quota preservation); on a failed local fetch the check retries once on the edge (`CLOUDFLARE_BROWSER_URL`/`CLOUDFLARE_BROWSER_TOKEN` in `.env`, covered by `backend/tests/test_browser_failover.py`). ⚠️ **Dormant on this machine:** the local ISP TCP/SNI-blocks `*.workers.dev` (other Cloudflare routes work fine), so the failover fails fast and local Playwright handles everything here; it engages on any network that doesn't block workers.dev |
| **Zone local-only rollback (2026-10-21, later)** | Portfolio zone decision: `sunilted.qzz.io` is reserved for the portfolio site. Removed for this project: Access app, `app./api.` tunnel DNS records (tunnel routes blanked to catch-all 404), `screenshots.*` R2 custom domain, beacon token + `NEXT_PUBLIC_SCREENSHOT_CDN_URL` (env cleared → API asset proxy). **Survived:** R2 `monitor-snapshots` + S3 token (zone-independent, round-trip verified) + 3.1 lifecycle rule; WAF/Bot-Fight/next-static cache rules left zone-wide (harmless + portfolio-friendly). Tunnel object kept (routes blank) — re-point it at a different zone/hostnames to resume public hosting |
| 9 Radar + URL Scanner (2026-10-21, via API) | Both verified live through the MCP OAuth session (Radar device-type summary + a real URL Scanner v2 scan of `example.com` submitted & polled). Built the **`security_scan` monitor mode**: `backend/app/services/security_scan.py` (submit → poll v2 → one-fact-per-line digest: `malicious=` / `categories=` / `tags=` / certificates / ASNs / `tech=`), mode added to `MONITOR_MODES` + `PLAIN_HTTP_MODES` + `LIST_DIFF_MODES`, js_required rejected in create/update validators, `workers/checks.py` dispatch branch, frontend option in `src/lib/modes.ts`, config `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_URLSCANNER_TOKEN`. 7 unit tests (`tests/test_security_scan.py`) + mode-census guards updated; **full backend suite 283 passed**, frontend 89 vitest + tsc clean, stack restarted & healthy. 🔑 Waiting on user: free URL Scanner API token (dashboard-only — OAuth can't mint tokens) |
| 5 Turnstile prep (2026-10-21, via API) | Widget `web-observer-public-form` created (Managed, non-interactive, hostname `clevertedz.workers.dev` placeholder). Sitekey `0x4AAAAAAFeyOcU7ZMZTIVRe`, secret stored in `.env`/`backend/.env` (`TURNSTILE_*`). Feature stays off — no public form exists; wire form + siteverify when one does |
| 6 share-cache Worker (2026-10-21, via API) | Worker `share-cache` uploaded (tag `6e9d4f9b00a04b888097efb926e343b3`, `CACHE_HOST` empty). Source `workers/share-cache/`. No route yet — attach routes on a public hostname when one exists (dormant locally anyway: workers.dev ISP-blocked) |

**Known deviations from the plan text below**

- **The API is deliberately *not* behind Access** (only `app.` is): gating `api.sunilted.qzz.io`
  would clap a login wall in front of every cross-origin call the UI makes. The plan's
  "UI only" option is the one we shipped.
- **Login is the Access page, not an auto-redirect to OTP**: creating a One-time PIN
  identity provider via API failed (`unknown connector "otp"`). OTP remains available
  as a login method on the Access login page — add it in dashboard → Zero Trust →
  Login methods if you want the one-click flow.
- **Rule 4.1 #2 blocks `/internal` for everyone** instead of "your IP only" — this
  account rarely updates, and a stale IP would lock out the app. Note blocking also
  covers the API host; the backend `/internal` routes are dev-only.
- ✅ **Tunnel is UP again** (2026-10-21): connector relaunched detached
  (`cloudflared tunnel run --token`, PID survives `restart-stack.ps1` sweeps), 4
  healthy QUIC connections via `bom11/maa05/bom12/maa03`. Public end-to-end
  verified: `api./health` → 200, `app.` → Access 302 login, `/.env` + `/internal`
  probes → 403 (WAF rules live). ⚠️ Still a *process, not a service* — run
  `.\scripts\cloudflare-tunnel.ps1 -Token '<token>'` **as administrator** once so
  it auto-starts at boot.
- ✅ **Session infrastructure** (same day): Redis (WSL2 Ubuntu) enabled via systemd
  and pinned alive; `restart-stack.ps1` run completed clean (Redis reachable,
  Frontend OK, API Health OK, Neon DB Ready OK).

---

## Phase 0 — Already wired

### 0.1 R2 Object Storage ✅ live

Raw HTML snapshots via `STORAGE_BACKEND=s3` (boto3, `backend/app/services/storage.py`).
Bucket `monitor-snapshots`, credentials in `backend/.env` (`S3_*`). Full setup +
ping test: [docs/guides/r2-setup.md](docs/guides/r2-setup.md).

- Free: **10 GB-month storage, 1M Class A + 10M Class B ops/mo, zero egress**
- ⚠️ The R2 token created 2026-10-21 has a **1-year TTL — rotate before 2027-10-21**
  (dashboard → R2 → Manage API Tokens) or snapshot writes fail with `Unauthorized`
  and runs are marked failed.

### 0.2 Cloudflare Tunnel ✅ live (2026-10-21 — connector running)

`cloudflared` serves the two public hostnames above to the local stack. No static
IP, no port-forwarding.

**Live as of 2026-10-21:** connector running detached
(`cloudflared tunnel run --token <token from data/cloudflared-token.txt>`),
tunnel metrics show 4 healthy connections (`bom11`, `maa05`, `bom12`, `maa03`),
and public traffic verified end-to-end. Note: it currently runs as a plain
process — run `.\scripts\cloudflare-tunnel.ps1 -Token '<token>'` once **as
administrator** to make it a boot-persistent Windows service.

- Ingress rules set via API: `api.` → `127.0.0.1:8002`, `app.` → `127.0.0.1:3000`, catch-all 404
- DNS CNAMEs set via API (proxied): `app.` + `api.` → `{tunnel-id}.cfargotunnel.com`

### 0.3 Web Analytics ✅ live (2026-10-21 — beacon token set)

Cookie-less, no-individual-tracking beacon on the Next.js UI. The component
(`frontend/src/components/cf-web-analytics-beacon.tsx`) is mounted in the root
layout and renders nothing until the token exists — zero network calls by default.

```env
# frontend/.env.local
NEXT_PUBLIC_CF_BEACON_TOKEN=<token from dashboard → Web Analytics → your site → Installation>
```

**Live config (2026-10-21, created via API):** site `app.sunilted.qzz.io` →
`NEXT_PUBLIC_CF_BEACON_TOKEN=<past 32-hex tags in frontend/.env.local>`.
Dashboard: **Analytics & Logs → Web Analytics** (15-min delayed). Cookie-free,
no individual tracking, unlimited beacon traffic on the free plan.

---

## Phase 1 — Zero Trust Access in front of the tunnel ✅ live (2026-10-21)

**Why first.** The tunnel doc already carries the warning: a tunnel makes the dev
machine reachable from the internet, and only Clerk JWTs / the internal token
stand between the world and your API. **Cloudflare Access** puts an
email-OTP / Google login *at Cloudflare's edge*, before any request reaches the
tunnel. Free for up to **50 users** — a solo workspace is nowhere near that.

- Free quota: **$0, up to 50 seats**, unlimited apps
- Effort: ~15 min in the dashboard, **zero code changes**

### Setup

1. Dashboard → **Zero Trust** (one-time: pick a team name, skip payment).
2. **Settings → Authentication → Login methods** → add **One-time PIN** (email
   OTP) and/or Google.
3. **Access → Applications → Add an application → Self-hosted**:
   - Application name: `Web Observer UI` — Domain: `app.sunilted.qzz.io`
   - Session duration: `24h` (re-login once a day at most)
4. Repeat for the API: name `Web Observer API`, domain `api.sunilted.qzz.io`.
5. On both apps, **Add a policy**: name `Just me`, Action **Allow**,
   Include → **Emails** → your address.

### The API-key caveat (read before sharing `mtw_` keys)

Access sits in front of *everything* on `api.` — including requests that
authenticate with `mtw_` API keys or the internal token. Programmatic callers
will hit the Access login page and get an HTML response instead of JSON. Options:

| Option | How |
| ------ | --- |
| UI only behind Access (simplest) | Delete the API application; protect only `app.` |
| API behind Access + bypass for API paths | On the API app, add a **Bypass** policy: Include → **Everyone**, and use path rules so `/api/v1/*` bypasses while the docs/UI paths stay gated |
| Machine-to-machine | Create **Access service tokens** (Access → Service Auth → Service Tokens) and send `CF-Access-Client-Id` / `CF-Access-Client-Secret` from scripts/cron jobs |

For solo use, "protect the UI, leave the API to its own token auth" is the right
default — the API already requires Clerk JWT or `INTERNAL_API_TOKEN`.

### Verify

```powershell
# From any browser (ideally another device): should show a Cloudflare login page
start https://app.sunilted.qzz.io

# Unauthenticated curl shows the Access interstitial, not the Next.js app
curl.exe -I https://app.sunilted.qzz.io
```

### Rollback

Access → Applications → delete the app (or toggle ** OFF **). Tunnel unaffected.

---

## Phase 2 — Cache Rules: edge-cache `/share/*` + static assets ✅ live (2026-10-21)

**Why.** `/share/{token}` pages (opaque-token, read-only, no login) are the only
public surface, and they're perfect CDN candidates. **Cache Rules** are free
(10 rules/zone) and cache them at Cloudflare's edge so repeat views never hit
your tunnel/PC. Static `_next/static` assets get the same treatment.

- Free quota: **10 cache rules**, unlimited edge cache on the free plan
- Effort: ~10 min, **zero code**

### Setup

Dashboard → zone `sunilted.qzz.io` → **Caching → Cache Rules → Create rule**.

**Rule 1 — share pages (short TTL so edits show up):**

| Field | Value |
| ----- | ----- |
| Name | `share-pages` |
| If | Hostname equals `app.sunilted.qzz.io` **and** URI Path starts with `/share` |
| Then | Eligible for cache ✓, Edge TTL: **5 minutes**, Browser TTL: **respect origin** |

**Rule 2 — Next.js static assets (immutable):**

| Field | Value |
| ----- | ----- |
| Name | `next-static` |
| If | Hostname equals `app.sunilted.qzz.io` **and** URI Path starts with `/_next/static/` |
| Then | Eligible for cache ✓, Edge TTL: **1 day** (files are content-hashed) |

⚠️ **Do not** cache anything under `/api/` or the SSE stream
(`/workspaces/{id}/monitors/{id}/events`) — those are live/authenticated. The two
rules above are path-scoped precisely so they can't catch it.

### Verify

```powershell
curl.exe -I https://app.sunilted.qzz.io/share/<a-real-token>
# second request must show:  cf-cache-status: HIT
```

### Rollback

Toggle the rule off. No stale-cache risk beyond the TTL you set.

---

## Phase 3 — R2 lifecycle rules + public screenshots bucket

Two independent freebies on the R2 account that's already live.

### 3.1 Lifecycle rules: free retention for snapshot objects ✅ live (2026-10-21)

`retention_job` purges *database rows*; R2 lifecycle rules purge the *objects*
at the bucket level with no cron, no code.

Dashboard → R2 → `monitor-snapshots` → **Settings → Object lifecycle rules**:

| Rule | Apply to prefix | Action |
| ---- | --------------- | ------ |
| `expire-snapshots-30d` | `workspaces/` | Delete objects **after 30 days** (matches `SNAPSHOT_RETENTION_DAYS=30` in `backend/app/config.py`) |

Free: lifecycle rules cost nothing and count no billable operations.

### 3.2 Public screenshots bucket ✅ done (2026-10-21 — one token-scope step pending)

Screenshots used to round-trip through FastAPI. Now they go public via CDN:

**Created via API:**

1. Bucket `monitor-screenshots-public` (APAC).
2. Custom domain `screenshots.sunilted.qzz.io` (DNS auto-created: CNAME →
   `public.r2.dev`, proxied; TLS free).
3. Cache rule `screenshots-cdn` added to the Phase 2 ruleset (edge TTL 1 day —
   keys carry the run id, so objects are immutable and safe to cache).

**Code (shipped):**

- `backend/app/config.py`: `S3_SCREENSHOT_BUCKET` (None = legacy proxy behaviour).
- `backend/app/services/storage.py`: key-prefix routing — `screenshots/…` keys
  go to the public bucket, `workspaces/…` + `brand-assets/…` stay private; reads,
  head and presigns all route the same way, so writers/readers always agree.
- `frontend/src/lib/api.ts`: `screenshotUrl()` — when
  `NEXT_PUBLIC_SCREENSHOT_CDN_URL` is set, screenshot `<img>` (visual diff,
  captured-content preview, monitor hero fallback) loads from the CDN instead of
  proxying bytes through `/api/v1/public/assets`; unset = unchanged proxy path.
- `frontend/.env.local` + `backend/.env`: `NEXT_PUBLIC_SCREENSHOT_CDN_URL`
  and `S3_SCREENSHOT_BUCKET` set.

⚠️ **Pending user action:** the R2 API token (`backend/.env` `S3_*`) is scoped to
`monitor-snapshots` only — new writes to `monitor-screenshots-public` will
Access-Deny until you re-create the token with **both buckets**
(dashboard → R2 → Manage API Tokens → edit permissions). Until then, screenshot
uploads to the CDN bucket fail silently (best-effort logging) and the UI falls
back to the API proxy; nothing else is affected. Old tokens: Object Read &
Write on `monitor-snapshots`; keep the 2027-10-21 TTL rotation note in mind.

- Free quota: same 10 GB / ops pool as Phase 0; custom domain free; `r2.dev`
  public URLs also exist but are rate-limited — use the custom domain.
- Effort: 10 min dashboard + ~30 lines backend/frontend.

### Verify / rollback

```powershell
# after wiring: upload one screenshot, then
curl.exe -I https://screenshots.sunilted.qzz.io/<key>.png   # 200, image/png
```

Rollback: point the backend back at the private bucket (`STORAGE_BACKEND=local`
or drop `S3_SCREENSHOT_BUCKET`). Old objects stay put.

---

## Phase 4 — Free zone security: custom rules, rate limiting, Bot Fight Mode ✅ live (2026-10-21)

All free, all dashboard-only, all protecting the two public hostnames.

### 4.1 WAF custom rules (free: 5 rules, no regex)

Zone → **Security → WAF → Custom rules**. Sensible starters:

| # | Rule | Expression (visual builder) | Action |
| - | ---- | ---------------------------- | ------ |
| 1 | Block junk probes | URI Path contains `.env` **or** `.git` | Block |
| 2 | Internal endpoints: only from known IPs | URI Path starts with `/internal` and IP Source Address **not in** `<your-ip>` | Block |

### 4.2 Rate limiting rule (free: 1 rule, Block only)

Zone → **Security → WAF → Rate limiting rules** — the free plan gets **1 rule**
(Block action, 10s/1min period, 1min/1h duration):

- If: Hostname equals `api.sunilted.qzz.io` → more than **100 requests / 10 seconds**
  from the same IP → **Block 1 minute**.

This is a blunt edge-level backstop *in front of* the app's per-principal Redis
limiter (`backend/app/rate_limit.py`), not a replacement for it.

### 4.3 Bot Fight Mode

Zone → **Security → Bots** → enable **Bot Fight Mode**. Free, one click, no
config on the free plan; challenges obvious bot traffic on both hostnames.

### Verify / rollback

```powershell
# 4.2: hammer the API from a loop; after ~100 req/10s expect 429s for a minute
# 4.1: curl.exe -I https://api.sunilted.qzz.io/.env   -> 403
```

Each rule toggles off independently; Bot Fight Mode is one switch.

---

## Phase 5 — Turnstile on public surfaces 🔑 keys ready (2026-10-21)

**Honest fit note:** today the only public pages are read-only share pages —
nothing to bot-protect yet. Wire Turnstile the moment an unauthenticated form
exists (a public "suggest a URL" box, share-page interactions, a waitlist).

- Status: widget **`web-observer-public-form`** created via API (Managed,
  non-interactive, hostname `clevertedz.workers.dev` — placeholder until a real
  host exists). Site key + secret stored in `.env` / `backend/.env`
  (`TURNSTILE_SITEKEY` / `TURNSTILE_SECRET_KEY`); no backend verify code yet,
  so the feature remains **off** (fail open) until a form exists.
- Free quota: **20 widgets, unlimited challenges, 10 hostnames/widget**,
  7-day analytics, no Enterprise-only tricks needed
- Effort: widget + ~30 lines frontend + one server verify call

### Setup

1. Dashboard → **Turnstile → Add widget**: type **Managed**, hostnames
   `app.sunilted.qzz.io`. Copy the **Site Key** (public) and **Secret Key**.
2. Frontend: load `https://challenges.cloudflare.com/turnstile/v0/api.js`,
   render the widget, submit `cf-turnstile-response` with the form.
3. Backend: verify server-side before trusting the form —

```python
import httpx

async def turnstile_ok(token: str, ip: str | None, secret: str) -> bool:
    r = await httpx.post(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data={"secret": secret, "response": token, "remoteip": ip},
    )
    return r.json().get("success", False)
```

Add `TURNSTILE_SECRET_KEY` to `backend/.env`; empty = feature off (fail open,
like the rest of the optional integrations).

### Rollback

Remove the widget from the form; empty secret disables verification.

---

## Phase 6 — Worker edge cache (+ KV) for share pages ✅ deployed (2026-10-21, no route yet)

**Why.** Phase 2's cache rules already cover most of it. Add a Worker when you
want *control*: per-token TTLs, cache warming on change, or trimming payloads
before they hit the edge cache. Workers free plan: **100,000 requests/day,
10 ms CPU, 50 subrequests, 128 MB memory** — enough for a cache/transform layer,
nowhere near enough for real compute.

> **Status:** Worker `share-cache` deployed via API (tag
> `6e9d4f9b00a04b888097efb926e343b3`), source in `workers/share-cache/`
> (`CACHE_HOST` var empty). Standalone today at `share-cache.clevertedz.workers.dev`
> (dormant locally — ISP blocks `workers.dev`). Wire `routes` + `CACHE_HOST`
> the moment this project has a public hostname again.

### Minimal edge-cache Worker

`workers/share-cache/src/index.js`:

```js
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    // Only intercept public, read-only paths — everything else passes through.
    const cacheable =
      url.hostname === "app.sunilted.qzz.io" &&
      (url.pathname.startsWith("/share/") ||
        url.pathname.startsWith("/_next/static/"));
    if (!cacheable) return fetch(request);

    const cache = caches.default;
    let res = await cache.match(request);
    if (res) return res;

    res = await fetch(request); // origin = the tunnel
    if (res.status === 200) {
      const cacheRes = res.clone();
      cacheRes.headers.append("Cache-Control", "public, max-age=300");
      ctx.waitUntil(cache.put(request, cacheRes));
    }
    return res;
  },
};
```

`workers/share-cache/wrangler.toml`:

```toml
name = "share-cache"
main = "src/index.js"
compatibility_date = "2026-10-01"
routes = ["app.sunilted.qzz.io/share/*", "app.sunilted.qzz.io/_next/static/*"]
```

```powershell
cd workers/share-cache
npx wrangler login          # once
npx wrangler deploy
```

### Optional KV binding

If the Worker starts deciding *what* to cache (e.g. warm cache when a change
lands), add read-heavy state to **Workers KV** — free: **100k reads/day,
1k writes/day, 1 GB, 25 MB values, 30s min cacheTtl**. The 1k-writes/day cap
makes KV a *cache*, never a queue — Redis keeps that job.

```toml
[[kv_namespaces]]
binding = "SHARE_CACHE"
id = "<create with: npx wrangler kv namespace create SHARE_CACHE>"
```

### Verify / rollback

```powershell
curl.exe -I https://app.sunilted.qzz.io/share/<token>   # cf-worker header + HIT on 2nd hit
```

Rollback: delete the route in `wrangler.toml` and `npx wrangler delete`.

---

## Phase 7 — Browser Rendering failover for `js_required` checks

**Fit.** The browser worker (`backend/app/workers/browser_checks.py` →
`playwright_job.py`) runs local Chromium. Cloudflare **Browser Rendering / Browser
Run** can do the same page-fetch + screenshot from their edge as a failover.

⚠️ **Free quota is tight** — plan around it:

| Limit (Workers Free) | Value |
| -------------------- | ----- |
| Browser time | **10 minutes/day** (429s until next UTC day when exhausted) |
| Browser timeout | 60 s |
| New instances | 1 every 20 s, 3 concurrent |
| Quick Actions REST | 1 request / 10 s |
| `/crawl` endpoint | 5 jobs/day, 100 pages per crawl |

This **cannot replace** Playwright — it's a failover for when the local Chromium
is down, or a trickle of low-priority `js_required` monitors.

### Setup sketch

1. A tiny Worker with the browser binding:

```js
export default {
  async fetch(request, env) {
    const { url } = await request.json();
    const browser = await env.BROWSER.launch();
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
    const html = await page.content();
    const shot = await page.screenshot({ type: "png" });
    await browser.close();
    return Response.json({ html, screenshot: null /* upload to R2 instead */ });
  },
};
```

```toml
# wrangler.toml
name = "browser-failover"
main = "src/index.js"
compatibility_date = "2026-10-01"
[browser]
binding = "BROWSER"
```

2. Backend flag: `CLOUDFLARE_BROWSER_URL` (+ a shared secret header) in
   `backend/app/config.py`; in the browser-check path, try the Worker first,
   fall back to Playwright on error/429. The existing SSRF guard
   (`backend/app/security/ssrf.py`) must allow-list the Worker's hostname.

### Verify / rollback

Stop local Chromium, run a `js_required` monitor — check should still succeed via
the Worker. Rollback: unset `CLOUDFLARE_BROWSER_URL` → pure Playwright again.

---

## Phase 8 — Email Routing: "email a URL to check it"

**Inbound** email is free (outbound Cloudflare email is Workers **Paid** —
Resend stays the sender). Fun trick for a monitoring product: email
`check@sunilted.qzz.io` with a URL in the subject → a Worker enqueues a run.

- Free quota: **200 routing rules/domain, 200 destination addresses**,
  25 MiB inbound
- Effort: Email Worker + one secret

### Setup

1. Zone → **Email → Email Routing** → enable, add a destination address, verify.
2. **Email Workers**: create a Worker with an `email()` handler:

```js
export default {
  async email(message, env, ctx) {
    const subject = message.headers.get("subject") || "";
    const url = subject.trim();
    if (!/^https?:\/\//.test(url)) { message.setReject("Not a URL"); return; }
    await fetch(`${env.API_BASE}/api/v1/monitors/by-url/run-now`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.INTERNAL_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url, workspace_hint: env.DEFAULT_WORKSPACE_ID }),
    });
  },
};
```

3. Route `check@sunilted.qzz.io` → that Worker.
4. Secrets: `npx wrangler secret put INTERNAL_API_TOKEN` (+ `API_BASE`).
   The API endpoint for "run now by URL" would be a small backend addition —
   today's flow is create-monitor (which runs immediately) or `run_now` on an
   existing monitor id.

### Verify / rollback

Email a known-good URL, watch the Logs page for a new run. Rollback: delete the
routing rule.

---

## Phase 9 — Radar API + URL Scanner as a monitor mode ✅ backend built (2026-10-21)

**Radar's API is free** (token required). **URL Scanner** can render any URL on
Cloudflare's infrastructure and return verdicts (`verdicts.overall.malicious`),
technologies, and page data — a natural future `security_scan` monitor mode
alongside `page_content` / `visual`.

> **Status:** both Radar and URL Scanner verified live through the MCP OAuth
> session (a real scan of `example.com` was submitted and its result polled).
> The new **`security_scan` monitor mode is in the backend**: submit → poll
> URL Scanner v2 → one-fact-per-line digest (`malicious=`, `categories=`,
> `tags=`, certificates, ASNs, `tech=` lines) that diffs with the standard
> LIST_DIFF pipeline. Files: `services/security_scan.py`,
> `models/entities.py` (`PLAIN_HTTP_MODES` + `LIST_DIFF_MODES`), schemas
> (js_required rejected), `workers/checks.py` (dispatch), `lib/modes.ts`
> (frontend option). 7 unit tests + the mode-census guards updated; full
> suite 283 passed.
> 🔑 **One human step remains:** create a free API token with URL Scanner
> permissions (Dashboard → My Profile → API Tokens) and paste it into
> `CLOUDFLARE_URLSCANNER_TOKEN` in `backend/.env`. Until then, runs of this
> mode fail clearly with `scan_not_configured` (fail open, like the rest).

### Setup (token + probe)

1. Dashboard → **My Profile → API Tokens → Create Token** (URL Scanner scope —
   OAuth connections cannot mint tokens, so this is dashboard-only).
2. Probe:

```powershell
curl.exe "https://api.cloudflare.com/client/v4/radar/http/summary/device_type?dateRange=7d&format=json" `
  -H "Authorization: Bearer <TOKEN>"

# submit a scan
curl.exe -X POST "https://api.cloudflare.com/client/v4/accounts/90917fcff9681d8b8da94ee10b0ac7fb/urlscanner/v2/scan" `
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" `
  -d '{"url":"https://example.com"}'
# then GET .../urlscanner/v2/result/<scan_id>  -> verdicts, tech stack, screenshot
```

3. Backend feature ✅ (see status above).

### Verify / rollback

Scan result JSON comes back with `success: true`. Rollback: revoke the token.

---

## Phase 10 — Optional / deprioritized (why each is skipped)

| Feature | Free quota | Verdict for this project |
| ------- | ---------- | ------------------------ |
| **D1** (SQLite) | 10 DBs, 500 MB/DB, 5 GB/account, 7-day Time Travel | Neon is the DB. No second source of truth worth the sync pain |
| **Queues** | Works on Workers Free (24 h retention, 128 KB msgs, 5k msg/s) | Redis + Dramatiq already do this with retries, leases, and dedup |
| **Cron Triggers + Hyperdrive** | 5 triggers/account; Hyperdrive: 10 DBs, ~20 pooled connections, 60s queries | Only worth it if you want digest/retention off Windows Task Scheduler. Digest needs Resend (fine, `fetch`), retention needs the DB — Hyperdrive bridges Workers → Neon |
| **Pages** | 500 builds/mo, 1 concurrent, 20k files | Frontend is SSR (Next.js + Clerk) → Pages is static-only. Real path is **Workers + OpenNext/vinext**; only bother when you want to stop hosting the UI on your PC |
| **Workers Logs** | 200k events/day, 3-day retention | Enable when the Phase 6 Worker exists (observability for it) |
| **Workers Paid** | $5/mo | Everything above stays free until a quota actually bites |

### Not free at all (don't chase)

- **Health Checks** — Pro plan+ (0 monitors on Free)
- **Cloudflare Email Sending (outbound)** — Workers Paid; Resend stays
- **Argo Smart Routing, Cache Reserve, Images, Stream, Load Balancing,
  Digital Experience Monitoring** — paid tiers
- **AI products** (Workers AI, AI Gateway, Vectorize, AI Crawler control) — excluded per project decision

---

## Free-quota cheat sheet (verified 2026-10-21)

| Product | Free quota | Phase |
| ------- | ---------- | ----- |
| R2 | 10 GB-mo · 1M Class A · 10M Class B · zero egress | 0, 3 |
| Tunnel | unlimited (connector model) | 0 |
| Web Analytics | unlimited beacon traffic | 0 |
| Access | 50 users, unlimited apps | 1 |
| Cache Rules | 10 rules | 2 |
| R2 lifecycle | unlimited rules, $0 | 3 |
| WAF custom rules | 5 (no regex) | 4 |
| Rate limiting | 1 rule, Block only | 4 |
| Bot Fight Mode | free, non-configurable | 4 |
| Turnstile | 20 widgets · unlimited challenges · 10 hostnames/widget | 5 |
| Workers | 100k req/day · 10 ms CPU · 50 subrequests · 100 Workers · 5 crons | 6–8 |
| Workers KV | 100k reads/day · 1k writes/day · 1 GB · 25 MB values | 6 |
| Browser Rendering | 10 min/day · 60 s timeout · 3 concurrent | 7 |
| Email Routing (inbound) | 200 rules/domain · 200 destinations · 25 MiB | 8 |
| Radar API / URL Scanner | free with API token | 9 |
| Hyperdrive | 10 DBs · ~20 connections | 10 |
| D1 | 10 DBs · 500 MB/DB · 5 GB/account | skipped |
| Queues | 24 h retention · 5k msg/s | skipped |
| Workers Logs | 200k events/day · 3-day retention | 10 |
| Pages | 500 builds/mo · 20k files · 100 projects | static-only |
