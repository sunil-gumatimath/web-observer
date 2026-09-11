<p align="center">
  <img src="../../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Phase 2 — Dashboard & Auth

Status: **Shipped** (historical record).

## What shipped

| Capability | Implementation |
| ---------- | -------------- |
| Next.js dashboard | Monitors list, monitor detail, alerts inbox, settings (`frontend/`) |
| Clerk auth | Sign-in/up via Clerk; API verifies session (`docs/guides/clerk-setup.md`) |
| Workspaces + membership | Workspace switcher, invite flow, per-workspace data isolation |
| RBAC (start) | Owner / admin / member / viewer roles, audit log (extended in Phase 6–7) |

## References

- `docs/auth-modes.md`, `docs/guides/clerk-setup.md`
- ADR 003 (Clerk auth)
