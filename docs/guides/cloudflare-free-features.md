# Cloudflare free features wired into Web Observer

Web Observer uses three Cloudflare free-tier features. All of them run at $0
under the free quota; each is independently optional.

| Feature | What it does here | Status |
| ------- | ----------------- | ------ |
| **R2 Object Storage** | Stores raw HTML snapshots (`STORAGE_BACKEND=s3`) — 10 GB free, zero egress | ✅ live (`backend/.env`) |
| **Web Analytics** | Cookie-less, no-individual-tracking beacon on the Next.js UI (visits, page views, Core Web Vitals) | 🔑 needs `NEXT_PUBLIC_CF_BEACON_TOKEN` |
| **Cloudflare Tunnel** | Exposes the local stack publicly (`app.sunilted.qzz.io` → :3000, `api.sunilted.qzz.io` → :8002) without port-forwarding | 🔑 needs the connector token (one click in the dashboard) |

Account: `Clevertedz@gmail.com` → Account ID `90917fcff9681d8b8da94ee10b0ac7fb`
Zone: `sunilted.qzz.io`.

## 1. R2 snapshots — done

Bucket `monitor-snapshots` with an Object-Read-&-Write token scoped to it,
credentials in `backend/.env` (`S3_*`). Details and the ping-test:
[docs/guides/r2-setup.md](r2-setup.md).

The S3 credentials live in `backend/.env` (gitignored). Token created
2026-10-21 with a 1-year TTL — rotate before **2027-10-21** (dashboard → R2 →
Manage API Tokens → Create API token) or snapshot writes start failing with
`Unauthorized` and runs are marked failed. On auth failure snapshots raise
`StorageError` and never fall back to local disk silently.

## 2. Web Analytics — needs one token

`frontend/.env.local`:

```env
NEXT_PUBLIC_CF_BEACON_TOKEN=<JS snippet token>
```

Where: dashboard → **Web Analytics → Web analytics sites → your hostname →
Installation → copy the JS snippet token** (the `token` value inside the
`data-cf-beacon` JSON). Empty (default) = the beacon never loads — zero
network calls, nothing tracked. The component:
[frontend/src/components/cf-web-analytics-beacon.tsx](../../frontend/src/components/cf-web-analytics-beacon.tsx)
, mounted in the root layout after `ThemeProvider`.

Note: because the token is only needed for the UI, local development does not
need it; it matters for the tunnel/deployed hostname.

## 3. Cloudflare Tunnel — one-time setup

`cloudflared` is installed (`winget install Cloudflare.cloudflared`).

1. Dashboard → **Zero Trust → Networks → Tunnels → Create tunnel** (name it
   `web-observer`).
2. Copy the connector token (the long `eyJ...` string, not the ID).
3. In the tunnel's **Public hostnames**, add:

| Subdomain | Domain | Service |
| --------- | ------ | ------- |
| `app` | `sunilted.qzz.io` | `http://127.0.0.1:3000` |
| `api` | `sunilted.qzz.io` | `http://127.0.0.1:8002` |

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
NEXT_PUBLIC_API_BASE_URL=https://api.sunilted.qzz.io

# backend/.env
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://app.sunilted.qzz.io
```

`restart-stack.ps1` loads both files, so a restart after the edit is enough.

Security note: a tunnel makes the dev machine reachable from the internet.
The API keeps its normal auth (Clerk JWT / internal dev token) and
`APP_ENV=production` guards — treat the public hostnames as production and
drop the internal-token mode before sharing links.
