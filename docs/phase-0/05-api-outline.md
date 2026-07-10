# API Outline — MVP

Status: **Draft approved for implementation**  
Style: REST + OpenAPI 3  
Base path: `/api/v1`

## Conventions

- JSON request/response  
- UUID path params  
- Auth: `Authorization: Bearer <Clerk JWT>` (Phase 2+); Phase 1 may use `X-Dev-User` / internal token  
- All resource access authorized via workspace membership  
- Error body: `{ "error_code": "...", "message": "...", "details": {} }`  
- Pagination: `limit`, `cursor` (or `offset` for MVP simplicity)

## Health

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | Liveness |
| GET | `/ready` | DB + Redis readiness |

## Workspaces

| Method | Path | Notes |
|--------|------|--------|
| GET | `/workspaces` | List memberships |
| POST | `/workspaces` | Create workspace |
| GET | `/workspaces/{id}` | Detail |
| GET | `/workspaces/{id}/members` | List members |

## Monitors

| Method | Path | Notes |
|--------|------|--------|
| GET | `/workspaces/{id}/monitors` | List |
| POST | `/workspaces/{id}/monitors` | Create (enforce quotas) |
| GET | `/workspaces/{id}/monitors/{monitor_id}` | Detail |
| PATCH | `/workspaces/{id}/monitors/{monitor_id}` | Update; may bump config_version |
| DELETE | `/workspaces/{id}/monitors/{monitor_id}` | Soft or hard delete + cascade policy |
| POST | `/workspaces/{id}/monitors/{monitor_id}/pause` | enabled=false |
| POST | `/workspaces/{id}/monitors/{monitor_id}/resume` | enabled=true; set next_run_at |
| POST | `/workspaces/{id}/monitors/{monitor_id}/run` | Manual enqueue |

### Create/update body (core)

```json
{
  "name": "Pricing page",
  "url": "https://example.com/pricing",
  "mode": "css_selector",
  "css_selector": "main .price",
  "schedule_interval_minutes": 60,
  "timezone": "UTC",
  "timeout_seconds": 30,
  "max_response_bytes": 2000000
}
```

## Runs

| Method | Path | Notes |
|--------|------|--------|
| GET | `/workspaces/{id}/monitors/{monitor_id}/runs` | History |
| GET | `/workspaces/{id}/runs/{run_id}` | Detail + error |

## Changes & diffs

| Method | Path | Notes |
|--------|------|--------|
| GET | `/workspaces/{id}/monitors/{monitor_id}/changes` | Change events |
| GET | `/workspaces/{id}/changes/{change_id}` | Detail + diff payload |
| GET | `/workspaces/{id}/snapshots/{snapshot_id}/content` | Signed URL or streamed normalized text |

## Notification channels

| Method | Path | Notes |
|--------|------|--------|
| GET | `/workspaces/{id}/notification-channels` | List |
| POST | `/workspaces/{id}/notification-channels` | Add email |
| DELETE | `/workspaces/{id}/notification-channels/{channel_id}` | Remove |

## Usage (MVP light)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/workspaces/{id}/usage` | Checks, storage, limits |

## Internal / admin (Phase 1)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/internal/seed` | Dev only |
| GET | `/internal/queues` | Optional diagnostics |

Not exposed publicly in production without hard auth.

## OpenAPI

- Generated from FastAPI routes  
- Frontend generates typed client in Phase 2  
