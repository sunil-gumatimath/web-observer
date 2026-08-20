# Web Observer — Architecture as UML

Generated from a code review of the `backend/` and `frontend/` trees.
Stack: FastAPI + Dramatiq/Redis workers, Next.js, Neon Postgres, Clerk, Resend, local-disk object storage, optional Playwright.

## 1. Component / Deployment Diagram

```mermaid
flowchart TB
    subgraph Client
        UI["Next.js Frontend :3000"]
    end
    subgraph APIProc["API process (uvicorn)"]
        API["FastAPI app.main:app\n/health /ready /api/v1/*"]
        AUTH["auth.py\nClerk JWT + mtw_ API keys + X-Internal-Token"]
    end
    subgraph SchedProc["Scheduler process"]
        SCHED["app.scheduler\nclaim_due_monitors + lease + reap"]
    end
    subgraph WorkerProc["Worker processes (dramatiq)"]
        HTTPW["run_http_check (http_checks)"]
        BROWW["run_browser_check (browser_checks)\nPlaywright"]
        NOTIFW["deliver_outbox_message (notifications)"]
        WEBHW["deliver_webhook_message (notifications)"]
        DIGEST["digest_job"]
        RETENT["retention_job"]
    end
    subgraph External
        CLERK["Clerk (auth + JWKS)"]
        RESEND["Resend (email)"]
        CHAT["Slack / Discord webhooks"]
        TARGET["Monitored web pages"]
    end

    NEO[("Neon Postgres")]
    REDIS[("Redis\nDramatiq broker")]
    OBJ[("Object storage\nlocal disk snapshots")]

    UI -->|"HTTPS + Bearer/JWT"| API
    API --> AUTH
    AUTH --> CLERK
    API --> NEO
    SCHED --> NEO
    SCHED -->|"enqueue_check"| REDIS
    API -->|"manual run / import"| REDIS
    REDIS -->|"http_checks"| HTTPW
    REDIS -->|"browser_checks"| BROWW
    REDIS -->|"notifications"| NOTIFW
    REDIS -->|"notifications"| WEBHW
    HTTPW -->|"fetch_url"| TARGET
    BROWW -->|"fetch_url_browser / screenshot"| TARGET
    HTTPW --> NEO
    BROWW --> NEO
    HTTPW --> OBJ
    BROWW --> OBJ
    NOTIFW --> NEO
    NOTIFW --> RESEND
    NOTIFW --> CHAT
    WEBHW --> TARGET
    DIGEST --> NEO
    DIGEST --> REDIS
    RETENT --> NEO
    RETENT --> OBJ
```

## 2. Backend Module Structure (Package Diagram)

```mermaid
flowchart LR
    subgraph App["backend/app"]
        main["main.py\nrouter wiring"]
        auth["auth.py\nprincipal + rbac"]
        db["db.py\nengine/Session"]
        cfg["config.py"]
        sch["schemas.py\nPydantic IO"]
        rt["routers/\nmonitors, workspaces,\nnotifications, enterprise, internal"]
        svc["services/\nfetcher, pipeline, diffing,\nextract, ai_summary, webhooks,\nemail, storage, usage, plans,\ndigest, ssrf helpers..."]
        wk["workers/\nbroker, checks, browser_checks,\nnotifications, webhooks,\nrun_guard, enqueue"]
        sec["security/ssrf.py"]
        sched["scheduler.py"]
        jobs["digest_job.py\nretention_job.py"]
    end
    rt --> auth
    rt --> svc
    rt --> db
    wk --> svc
    wk --> db
    svc --> sec
    svc --> db
    sched --> wk
    sched --> db
    jobs --> svc
    main --> rt
    main --> db
```

## 3. Data Model (Class Diagram / ERD)

```mermaid
classDiagram
    class User {
        +UUID id
        +String clerk_user_id
        +String email
    }
    class Workspace {
        +UUID id
        +String name
        +String plan  free|pro|business|enterprise
        +String digest_cadence  none|daily|weekly
        +bool ai_summaries_enabled
    }
    class WorkspaceMember {
        +UUID id
        +UUID workspace_id
        +UUID user_id
        +String role  owner|admin|member|viewer
    }
    class Monitor {
        +UUID id
        +UUID workspace_id
        +String url
        +String mode  page_content|site_links|product_price|list_items
        +int schedule_interval_minutes
        +bool enabled
        +int config_version
        +DateTime next_run_at
        +String lease_owner
    }
    class MonitorConfigVersion {
        +UUID id
        +UUID monitor_id
        +int version
    }
    class MonitorRun {
        +UUID id
        +UUID monitor_id
        +UUID workspace_id
        +String status  scheduled|queued|running|succeeded|failed|cancelled|skipped
        +String content_hash
        +UUID snapshot_id
    }
    class Snapshot {
        +UUID id
        +UUID monitor_id
        +UUID run_id
        +String content_hash
        +String raw_object_key
        +String text_object_key
    }
    class ChangeEvent {
        +UUID id
        +UUID monitor_id
        +UUID run_id
        +UUID new_snapshot_id
        +UUID previous_snapshot_id
        +String diff_summary
        +String ai_summary
        +bool is_noise
        +bool is_read
    }
    class NotificationChannel {
        +UUID id
        +UUID workspace_id
        +String type  email|slack|discord
        +String address
    }
    class NotificationOutbox {
        +UUID id
        +UUID change_event_id
        +UUID channel_id
        +String status  pending|processing|sent|failed
    }
    class NotificationDelivery {
        +UUID id
        +UUID outbox_id
        +String provider_message_id
    }
    class WebhookEndpoint {
        +UUID id
        +UUID workspace_id
        +String url
        +String secret
    }
    class WebhookDelivery {
        +UUID id
        +UUID endpoint_id
        +String event_type
    }
    class ApiKey {
        +UUID id
        +UUID workspace_id
        +String key_hash
        +String key_prefix
    }
    class AuditLog {
        +UUID id
        +UUID workspace_id
        +String action
    }
    class UsageCounter {
        +UUID id
        +UUID workspace_id
        +int checks_count
        +int notifications_count
        +int storage_bytes
    }

    User "1" --> "*" WorkspaceMember
    Workspace "1" --> "*" WorkspaceMember
    Workspace "1" --> "*" Monitor
    Workspace "1" --> "*" NotificationChannel
    Workspace "1" --> "*" WebhookEndpoint
    Workspace "1" --> "*" ApiKey
    Workspace "1" --> "*" AuditLog
    Workspace "1" --> "*" UsageCounter
    Monitor "1" --> "*" MonitorConfigVersion
    Monitor "1" --> "*" MonitorRun
    MonitorRun "1" --> "0..1" Snapshot
    ChangeEvent "1" --> "0..1" Snapshot : new (new_snapshot_id)
    ChangeEvent "1" --> "0..1" Snapshot : previous (previous_snapshot_id)
    ChangeEvent "1" --> "*" NotificationOutbox
    NotificationChannel "1" --> "*" NotificationOutbox
    NotificationOutbox "1" --> "*" NotificationDelivery
    WebhookEndpoint "1" --> "*" WebhookDelivery
```

## 4. Sequence Diagram — Scheduled Live Check

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant DB as Postgres
    participant R as Redis
    participant W as Check Worker
    participant G as ssrf/domain_guard
    participant F as Fetcher / Playwright
    participant P as Pipeline
    participant OBJ as Object Storage
    participant N as Notification Worker
    participant WH as Webhook Worker
    participant EXT as Resend/Slack/Targets

    S->>DB: claim_due_monitors (SELECT .. FOR UPDATE SKIP LOCKED)
    DB-->>S: due monitors (lease 60s, next_run bumped)
    S->>R: enqueue_check(run_id, needs_browser)
    R->>W: run_http_check / run_browser_check
    W->>DB: load MonitorRun + Monitor
    W->>G: assert_domain_allowed + acquire_domain_slot
    W->>F: fetch_url / fetch_url_browser
    F-->>W: FetchResult(text, status_code, latency)
    W->>P: apply_fetch_result(monitor, run, result)
    P->>OBJ: put_bytes(raw html + normalized .txt)
    P->>DB: insert Snapshot (content_hash)
    P->>DB: find prev SUCCEEDED run (same config_version)
    alt no prev run
        P-->>W: PipelineResult(is_baseline=true)
    else same hash / similar ahash
        P-->>W: PipelineResult(unchanged=true)
    else change detected
        P->>DB: insert ChangeEvent (+ AI summary)
        P->>DB: insert NotificationOutbox per channel
        P->>DB: insert WebhookDelivery per endpoint
        W->>R: deliver_outbox_message.send(oid)
        W->>R: deliver_webhook_message.send(wid)
        R->>N: deliver email/slack/discord
        N->>EXT: send via Resend/Slack/Discord
        R->>WH: POST signed (X-MTW-Signature) payload
    end
    W->>DB: RunStatus = succeeded/failed + run_guard outcome
    W->>G: release_domain_slot
```

## 5. Sequence Diagram — Manual / API-Triggered Run

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as FastAPI (routers)
    participant DB as Postgres
    participant R as Redis
    participant W as Check Worker (as above)

    UI->>API: POST /monitors {url, mode, ...}
    API->>API: require_workspace_member + plan quota
    API->>API: validate_url_for_fetch (SSRF)
    API->>DB: insert Monitor + MonitorConfigVersion v1
    API-->>UI: 201 MonitorOut

    UI->>API: POST /monitors/{id}/run
    API->>DB: assert_can_run_check (usage quota)
    API->>DB: insert MonitorRun (status=queued)
    API->>R: enqueue_check(run_id, needs_browser)
    API-->>UI: 202 ManualRunOut (run_id)
    R->>W: (continues as Sequence 4)
```

## 6. Pipeline Decision Flow (Activity Diagram)

```mermaid
flowchart TD
    A[FetchResult] --> B{status >= 400?}
    B -->|yes| F1[Run FAILED\nhttp_client/server_error]
    B -->|no| C[extract_normalized by mode\npage_content / site_links / product_price / list_items]
    C --> D{extraction OK\nand non-empty?}
    D -->|no| F2[Run FAILED\nextraction_failed]
    D -->|yes| E[content_hash + store raw + Snapshot]
    E --> G{prev SUCCEEDED run\nsame config_version?}
    G -->|none| H[(BASELINE\nset, no alert)]
    G -->|exists| I{hash equal\nor ahash similar?}
    I -->|yes| J[(UNCHANGED\nno alert)]
    I -->|no| K[compute diff / list diff / visual diff]
    K --> L[enrich_change -> AI summary\ninsert ChangeEvent]
    L --> M[queue NotificationOutbox\nper enabled channel]
    M --> N[enqueue WebhookDelivery\nper enabled endpoint]
    N --> O[(CHANGE DETECTED\nnotify out)]
```

## Notes

* **Auth modes** (`auth.py`): Clerk JWT (`Authorization: Bearer`), workspace API keys (`mtw_...`), and internal token (`X-Internal-Token`) for dev/smoke tests. RBAC via `require_workspace_member` / `require_role(min_role)`.
* **Mode routing** (`workers/enqueue.py`): `visual` mode or `js_required` flag routes to the `browser_checks` queue (Playwright); everything else goes to `http_checks`.
* **Outbox pattern**: change detection writes `NotificationOutbox` + `WebhookDelivery` rows, then workers fan out. This decouples detection from delivery and gives at-least-once send with retry (`max_retries=5`).
* **SSRF guard** (`security/ssrf.py`): blocks private/loopback/link-local/metadata IPs and credentialed URLs before any fetch; redirects are re-validated in the fetcher.
* **Quotas/plans** (`services/usage.py`, `services/plans.py`): daily check/notification/storage counters per workspace, gated by plan.
* **Lease + reaper**: scheduler claims monitors with a 60s lease; `run_reaper` recovers stuck runs so HA scheduler/workers don't double-run.
