# Phases 6 & 7 — Monetization, Bulk Workflows, Enterprise

## Phase 6

| Feature | Endpoint / notes |
|---------|------------------|
| Bulk import JSON/CSV | `POST /api/v1/workspaces/{id}/monitors/import` |
| Export monitors | `GET .../export/monitors?format=json\|csv` |
| Export changes | `GET .../export/changes` |
| API keys | `GET/POST/DELETE .../api-keys` (`mtw_...` Bearer) |
| Signed webhooks | `POST .../webhooks` + `X-MTW-Signature` |
| Webhook deliveries | `GET .../webhook-deliveries` |
| Plans | `GET /api/v1/billing/plans` |
| Checkout (sim/Stripe) | `POST .../billing/checkout` |

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
| Member role update | `PATCH .../members/{user_id}` (owner) |
| Audit log | `GET .../audit-logs` |
| Adaptive scheduling | stretches interval after quiet runs |
| Scale path | separate queues/workers already; K8s/Kafka deferred |

## Migration

`alembic upgrade head` → **006**
