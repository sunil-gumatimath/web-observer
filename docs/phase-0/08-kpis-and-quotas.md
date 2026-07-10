# KPIs, Quotas, and Retention Defaults

Status: **Approved as beta defaults (configurable)**

## Private-beta KPIs

| Metric | Target |
|--------|--------|
| Successful eligible checks | ≥ 99% |
| Lightweight checks within 15s | ≥ 95% |
| Checks start within 5 min of schedule | ≥ 99% |
| Duplicate notifications | < 1 / 10,000 deliveries |
| Alerts rated useful | ≥ 90% |
| Cross-workspace incidents | 0 |
| Successful SSRF to blocked targets | 0 |
| 4-week workspace retention | ≥ 30% |

## Product metrics to track

- Active monitors / workspaces  
- Monitored domains  
- Checks per day  
- Changes detected  
- Alert CTR / diff views  
- Schedule → notification latency  
- Monitors paused/deleted after noise  
- Noise feedback rate  
- WAU/MAU retention  
- Trial → paid (when billing exists)  

## Cost metrics

- Cost / 1,000 HTTP checks  
- Cost / 1,000 browser checks (later)  
- Storage $ / workspace  
- Notification $ / workspace  
- AI $ / summary (later)  
- Infra $ / active monitor  

## Initial workspace quotas (beta defaults)

| Limit | Default |
|-------|---------|
| Min check interval | 15 minutes (5 min for trusted internal) |
| Max monitors / workspace | 25 |
| Max checks / day / workspace | 500 |
| Max browser checks / day | 0 (until Phase 3) |
| Max response size | 2 MB |
| Max snapshot storage / workspace | 1 GB |
| Max notification deliveries / day | 200 |
| Per-domain concurrency | 2 |
| Per-domain request rate | 10 / minute |
| Global worker concurrency | env-tuned (e.g. 10 HTTP) |
| API rate limit | 60 req / min / user |
| Snapshot retention | 30 days raw |

Admins may raise limits for selected beta workspaces.

## Observability correlation IDs

Always log (never log page body / secrets):

- `workspace_id`  
- `monitor_id`  
- `run_id`  
- `change_event_id`  
- `delivery_id`  
