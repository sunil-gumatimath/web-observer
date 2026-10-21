<p align="center">
  <img src="../../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# n8n & Zapier examples

Two ways to plug Web Observer into an automation: **signed webhooks** (push)
and the **REST API** (pull).

## Signed webhook → automation

1. Create a webhook in the app (**Settings → Webhooks**). Available on every
   plan, including `free`.
2. Copy the **secret** (shown once — it cannot be recovered afterwards) and the
   URL to receive events.
3. In n8n / Zapier, create a **Webhook** trigger (or an HTTP request receiver).
4. Verify the signature before trusting the payload.

### Signing contract

```text
raw_body   = the exact request body, byte for byte (do not re-serialize)
timestamp  = header X-MTW-Timestamp  (Unix seconds, as a string)
signature  = header X-MTW-Signature  (lowercase hex)

expected = hex( HMAC_SHA256( key = webhook_secret,
                             message = timestamp + "." + raw_body ) )
```

Compare with a **constant-time** equality check. Reject the request if
`|now - timestamp|` exceeds your replay window (5 minutes is typical) — the
timestamp is inside the signed message, so a replayed body with a fresh
timestamp will not verify.

```python
import hmac, hashlib, time

def verify(secret: str, raw_body: bytes, timestamp: str, signature: str) -> bool:
    if abs(int(time.time()) - int(timestamp)) > 300:
        return False
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Payload shape

The body is a JSON envelope:

```json
{
  "id": "<delivery uuid>",
  "type": "change.detected",
  "created_at": "2026-10-21T09:12:33.123456+00:00",
  "data": {
    "change_id": "<change uuid>",
    "monitor_id": "<monitor uuid>",
    "monitor_name": "Pricing",
    "url": "https://example.com/pricing",
    "summary": "3 lines changed",
    "ai_summary": "Price dropped from USD 29.99 to USD 24.99",
    "title": "Price drop",
    "impact": "high",
    "category": "pricing",
    "mode": "product_price",
    "screenshot_path": "screenshots/<monitor_id>/<run_id>.png"
  }
}
```

`data.ai_summary`, `data.title`, `data.impact` and `data.category` are `null`
when no AI provider is configured. `data.screenshot_path` is `null` when
screenshots are off for that monitor.

Deliveries are **at-least-once**: a failed delivery is retried with
exponential backoff (30s → 2m → 8m → 30m, up to 5 attempts) and a
`Retry-After` response header is honoured. Make your handler idempotent on
`data.change_id`.

Every delivery is listed in **Settings → Webhooks → Deliveries** and can be
re-queued manually via
`POST /api/v1/workspaces/{id}/webhook-deliveries/{delivery_id}/retry`.

## API key → create monitors

```http
POST /api/v1/workspaces/{workspace_id}/monitors
Authorization: Bearer mtw_...
Content-Type: application/json

{ "name": "Pricing", "url": "https://example.com", "mode": "page_content", "schedule_interval_minutes": 60 }
```

API keys are created in **Settings → API keys** and are shown once. They are
hashed at rest (HKDF-derived, `v2$` scheme) and can be revoked at any time.

## Bulk CSV import

```http
POST /api/v1/workspaces/{id}/monitors/import
Authorization: Bearer mtw_...

{ "csv_text": "name,url,mode\nDocs,https://example.com/docs,page_content\n" }
```

## Zapier outline

1. Trigger: **Catch Hook** (the Web Observer webhook)  
2. Action: Slack / Email / Google Sheet row  

## More automation hooks

- Bulk pause/resume: `POST /api/v1/workspaces/{workspace_id}/monitors/pause-all` (and `.../resume-all`) with `Authorization: Bearer mtw_...`.
- Trigger a check on demand: `POST /api/v1/workspaces/{workspace_id}/monitors/{monitor_id}/run` (returns `202` with the `run_id`).
- Change activity for reports: `GET /api/v1/workspaces/{workspace_id}/changes/activity?days=30` returns per-day counts plus a per-category breakdown (`by_category`, null → `uncategorized`).
- Run history for reports: `GET /api/v1/workspaces/{workspace_id}/runs?outcome=failed` and `GET /api/v1/workspaces/{workspace_id}/export/runs?format=csv` (same filters, 20k-run cap).
- Public read-only monitor page: `GET /api/v1/public/share/{token}` — no auth, for a shareable status board.

## Related

- [docs/local-dev.md](../local-dev.md) — run the API locally
- [docs/architecture.md](../architecture.md) — how the outbox and webhook delivery work
