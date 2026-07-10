# n8n & Zapier examples

## Signed webhook → automation

1. Create a webhook in the app (**Settings → Webhooks**) on **pro+**.  
2. Copy the **secret** (shown once) and URL to receive events.  
3. In n8n / Zapier, create a **Webhook** trigger (or HTTP request receiver).  
4. Verify signature:

```text
payload = raw request body
timestamp = header X-MTW-Timestamp
signature = header X-MTW-Signature
expected = HMAC_SHA256(secret, timestamp + "." + payload)
```

Event type: `change.detected` with monitor name, URL, summaries.

## API key → create monitors

```http
POST /api/v1/workspaces/{workspace_id}/monitors
Authorization: Bearer mtw_...
Content-Type: application/json

{ "name": "Pricing", "url": "https://example.com", "mode": "whole_page", "schedule_interval_minutes": 60 }
```

## Bulk CSV import

```http
POST /api/v1/workspaces/{id}/monitors/import
Authorization: Bearer mtw_...

{ "csv_text": "name,url,mode\nDocs,https://example.com/docs,whole_page\n" }
```

## Zapier outline

1. Trigger: Catch Hook (MTW webhook)  
2. Action: Slack / Email / Google Sheet row  
