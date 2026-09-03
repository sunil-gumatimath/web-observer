<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Phases 6 & 7 — Monetization, Bulk Workflows, Enterprise

## Phase 6

| Feature | Endpoint / notes |
|---------|------------------|
| Bulk import JSON/CSV | `POST /api/v1/workspaces/{id}/monitors/import` |
| Export monitors | `GET /api/v1/workspaces/{id}/export/monitors?format=json\|csv` |
| Export changes | `GET /api/v1/workspaces/{id}/export/changes` |
| API keys | `GET/POST/DELETE /api/v1/workspaces/{id}/api-keys` (`mtw_...` Bearer) |
| Signed webhooks | `POST /api/v1/workspaces/{id}/webhooks` + `X-MTW-Signature` |
| Webhook deliveries | `GET /api/v1/workspaces/{id}/webhook-deliveries` |
| Plans | `GET /api/v1/billing/plans` |
| Checkout (sim/Stripe) | `POST /api/v1/workspaces/{id}/billing/checkout` |

### Plans (defaults)

- **free** — 10 monitors, 200 checks/day, no webhooks/API keys  
- **pro** — 100 monitors, webhooks + API keys  
- **business** / **enterprise** — higher limits  

Without `STRIPE_SECRET_KEY`, checkout **simulates** plan upgrade (local/dev).

### Webhook verification

```
signed = HMAC_SHA256(secret, "{timestamp}." + raw_body)
header X-MTW-Timestamp, X-MTW-Signature
```

### Automation examples

See `docs/integrations/n8n-zapier.md`.

## Phase 7

| Feature | Notes |
|---------|--------|
| RBAC | roles: owner, admin, member, viewer (`require_role`) |
| Member role update | `PATCH /api/v1/workspaces/{id}/members/{user_id}` (owner) |
| Audit log | `GET /api/v1/workspaces/{id}/audit-logs` |
| Adaptive scheduling | stretches interval after quiet runs |
| Scale path | separate queues/workers already; K8s/Kafka deferred |

## Migration

`alembic upgrade head` (Phase 6–7 schema is introduced in revision `004_phase6_7_enterprise`; project head is `012_add_ai_intelligence_fields`).

## Conditional alerting (migration `011`, post-roadmap)

Per-monitor `alert_config` JSONB — evaluated by `should_alert()` (`backend/app/services/conditional.py:26`) after diff, before notify. Unmet thresholds mark the change `is_noise=true` with a reason (kept in dashboard, excluded from notifications/digests). Empty/missing config = alert on any hash difference. Changing `alert_config` does not bump `config_version` (thresholds don't affect the baseline).

| Key | Applies to | Meaning |
|-----|------------|---------|
| `price_below` / `price_above` (number) | `product_price` | Alert only when parsed price is below / above the threshold |
| `percent_change` (number) | `product_price`, `json_field`, `page_content` | Minimum % change required to alert |
| `list_min_added` / `list_min_removed` (int) | `list_items`, `site_links`, `rss_feed` | Minimum added/removed items required |
| `min_diff_chars` (int) | any | Minimum character-length delta required |
| `regex_must_match` (str) | any | Alert only if new content matches regex (case-insensitive) |
| `regex_must_not_match` (str) | any | Suppress when new content matches regex (case-insensitive) |

Set via `POST/PATCH /api/v1/.../monitors` body field `alert_config`, or bulk import (`alert_config` column in CSV/JSON — see `backend/app/services/bulk_import.py:54`). Invalid values fail open (threshold ignored, alert proceeds).
