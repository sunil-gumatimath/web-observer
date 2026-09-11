<p align="center">
  <img src="../../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Phase 1 — Core Detection Pipeline

Status: **Shipped** (historical record).

## What shipped

| Capability | Implementation |
| ---------- | -------------- |
| SSRF-safe fetch | `app/services/http_fetch.py` (target allowlist/blocklist, redirect limits) |
| Extract / normalize / hash / diff | `app/services/pipeline.py` (+ `readability.py`, category/type classification) |
| Baseline rule | First successful run sets the baseline — no alert on baseline |
| Runs / snapshots / change events | `MonitorRun`, `Snapshot`, `ChangeEvent` (`docs/phases/phase-00-erd.md`) |
| Outbox + notifications | Transactional outbox → `notifications` queue (email via Resend) |
| Quotas | Per-workspace check limits, domain rate limit / concurrency |

## References

- `docs/phases/phase-00-architecture.md`, `docs/phases/phase-00-threat-model.md`
- ADR 001 (fetch pipeline), ADR 002 (diff/baseline), ADR 004 (outbox)
