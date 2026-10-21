# Cloudflare Web Analytics

Web Observer can report anonymous usage of the UI through **Cloudflare Web
Analytics** — free, cookie-less, and with no individual-visitor tracking.

The feature is **off by default**. The beacon component renders `null` when no
token is configured, so the app makes **zero** analytics network calls until
you opt in.

---

## 1. What it collects

Cloudflare Web Analytics is built for privacy by default:

| | |
| --- | --- |
| Cookies | **None** |
| Cross-site tracking | **None** |
| Fingerprinting | **None** |
| Personal data | **None** — no IP addresses, no user agents stored |
| Data retention | 24 hours, aggregated |

It reports aggregate page views, unique visitors, referrers, and Core Web
Vitals (LCP, CLS, INP) for the hostname the script is served from.

Because it is aggregate-only, it tells you *how many* people used a page, not
*who* they are. It never sees monitor URLs, workspace data, or anything the
backend stores — the beacon only fires on page loads of the frontend.

> The beacon is loaded from `static.cloudflareinsights.com`. If you run the
> app in an air-gapped or privacy-stripped environment, leave the token unset.

## 2. Turn it on

### Get the token

Dashboard → **Web Analytics** → **Add a site** → enter the hostname the UI is
served from (e.g. `app.sunilted.qzz.io`, or `localhost` for a local check) →
copy the **token** from the installation snippet. It is the `token` value
inside the `data-cf-beacon` JSON, not the whole snippet.

### Set the env var

`frontend/.env.local`:

```env
NEXT_PUBLIC_CF_BEACON_TOKEN=<token from the dashboard>
```

### Restart and verify

```powershell
powershell -File .\scripts\restart-stack.ps1
```

Then load the UI and check **Web Analytics → your site** in the dashboard after
a minute or two. In the browser, the network tab should show a request to
`static.cloudflareinsights.com/beacon.min.js` and a beacon POST — that request
is the proof the token took effect.

### Turn it off

Remove the line (or set it to an empty string) and restart. The component
short-circuits on an empty token, so no script is injected at all.

## 3. How it is wired

| Piece | Where |
| ----- | ----- |
| Beacon component | `frontend/src/components/cf-web-analytics-beacon.tsx` |
| Mounted in the root layout | `frontend/src/app/layout.tsx` |
| Env read | `frontend/src/lib/config.ts` (`cfBeaconToken`) |

The component uses `next/script` with `strategy="lazyOnload"`, so the beacon
loads *after* the app is interactive and stays out of the critical rendering
path — the same defer-first behaviour as Cloudflare's official snippet.

## 4. Notes

- **Local development does not need the token.** It only matters for the
  tunnel / deployed hostname. If you set it for `localhost`, your local
  browsing shows up in the same dashboard as production traffic.
- **The backend is not involved.** There is no server-side analytics code; the
  only analytics-shaped endpoint in the API is `GET /metrics`, which serves
  Prometheus-compatible metrics for *your own* monitoring and is unrelated to
  Web Analytics.
- **Self-hosting your own analytics** (e.g. Umami, Plausible) works too — the
  component is the only place a third-party script is injected, so swapping it
  is a one-file change.

## 5. Related

- [docs/guides/cloudflare-free-features.md](cloudflare-free-features.md) — the
  other free-tier Cloudflare features (R2 snapshots, R2 screenshot CDN,
  Tunnel, Browser Rendering failover, URL Scanner, Workers)
- [docs/local-dev.md](../local-dev.md) — running the frontend with env vars
