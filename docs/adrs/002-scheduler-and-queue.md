# ADR 002: Scheduler and Queue

## Status

Accepted

## Context

Monitors need reliable recurring checks without one OS cron job per monitor, with safe multi-instance claiming and retries.

## Decision

1. **Scheduler**: PostgreSQL-driven. Poll monitors where `next_run_at <= now()`, claim with `FOR UPDATE SKIP LOCKED` or timed lease, set next run (with jitter), enqueue job.  
2. **Queue**: Redis + Dramatiq.  
3. **Queues**: `http_checks`, `notifications`, and **`browser_checks`** (Playwright JS-rendered; separate worker, `--threads 1` on Windows).  
4. **Idempotency**: unique key per scheduled execution; one active run per monitor; change event + outbox in one DB transaction.

## Alternatives considered

| Option | Why not (MVP) |
|--------|----------------|
| Celery Beat | Extra complexity; still need DB truth for next_run_at |
| OS cron per monitor | Does not scale; hard multi-tenant ops |
| Only Redis schedules | Weaker durability/queryability for due work |

## Consequences

- Scheduler process is a first-class service.  
- Workers are horizontally scalable.  
- DB is source of truth for “when to run next.”
