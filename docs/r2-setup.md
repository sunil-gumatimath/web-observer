# Cloudflare R2 for snapshots (10GB free, zero egress)

Backend already speaks S3/R2 via boto3 (`backend/app/services/storage.py:70`,
`backend/app/config.py:58-66`). No code change needed — only env + secrets.

## Secrets required (you create these)

From Cloudflare dashboard → R2:

| Secret / var | Where to get it |
| --- | --- |
| `S3_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` — R2 → Overview shows Account ID |
| `S3_ACCESS_KEY` | R2 → Manage R2 API Tokens → Create token (Object Read & Write, scope to bucket) → Access Key ID |
| `S3_SECRET_KEY` | Same token → Secret Access Key (shown once, store it) |
| `S3_BUCKET` | R2 → Create bucket, e.g. `monitor-snapshots` (plain env, not secret, but keep it alongside your other secrets) |
| `S3_REGION` | `auto` (plain env default, no secret needed) |
| `STORAGE_BACKEND` | `s3` (plain env) |

Free quota: 10GB storage, 1M Class-A + 10M Class-B ops/mo, zero egress.

## 1. Create bucket + token (Cloudflare)

1. `dash.cloudflare.com` → R2 → Create bucket `monitor-snapshots` (any region, private).
2. R2 → Manage R2 API Tokens → Create API token:
   - Permissions: Object Read & Write
   - Scope: Apply to `monitor-snapshots` only
   - TTL: no expiry (or 1 year + rotate)
3. Copy Account ID, Access Key ID, Secret.

## 2. Local dev test

`backend/.env`:

```env
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_ACCESS_KEY=<key-id>
S3_SECRET_KEY=<secret>
S3_BUCKET=monitor-snapshots
S3_REGION=auto
```

```powershell
cd backend
.\.venv\Scripts\python -c "from app.services import storage; print(storage.put_bytes(key='workspaces/_ping/test.html', data=b'r2-ok'))"
.\.venv\Scripts\python -c "from app.services.storage import get_bytes; print(get_bytes('workspaces/_ping/test.html'))"
```

Delete the `_ping` key in R2 dashboard after.

## 3. Rollback

Set `STORAGE_BACKEND=local`. Old snapshots stay in R2; new checks write to local disk.
