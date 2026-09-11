# Phase Records

Historical phase documentation, from discovery through enterprise. These are
frozen records of what each phase planned and shipped. For current behavior see
the reference docs under [docs/](../README.md) (architecture, local-dev, guides).

## Phase 0 — Validation & Architecture

| Doc | Description |
| ----- | ------------- |
| [phase-00-product-scope.md](./phase-00-product-scope.md) | Vision, MVP scope, non-goals |
| [phase-00-mvp-user-flow.md](./phase-00-mvp-user-flow.md) | End-to-end user + system flow |
| [phase-00-architecture.md](./phase-00-architecture.md) | Diagrams, lifecycle, retries |
| [phase-00-erd.md](./phase-00-erd.md) | Core data model |
| [phase-00-threat-model.md](./phase-00-threat-model.md) | SSRF + tenant isolation |
| [phase-00-api-outline.md](./phase-00-api-outline.md) | REST outline |
| [phase-00-backlog.md](./phase-00-backlog.md) | Implementation backlog |
| [phase-00-kpis-and-quotas.md](./phase-00-kpis-and-quotas.md) | Metrics and limits |

Local setup & ops live in
[../operations/local-setup-and-ops.md](../operations/local-setup-and-ops.md).

## Later phases

| Doc | Description |
| ----- | ------------- |
| [phase-01-core-detection.md](./phase-01-core-detection.md) | Core detection pipeline (SSRF-safe fetch → diff → alerts) |
| [phase-02-dashboard-auth.md](./phase-02-dashboard-auth.md) | Next.js dashboard + Clerk auth + workspaces |
| [phase-03-browser-and-js.md](./phase-03-browser-and-js.md) | Reliability & JavaScript rendering (Playwright) |
| [phase-04-structured-and-visual.md](./phase-04-structured-and-visual.md) | Structured & visual monitor modes |
| [phase-05-ai-and-alerts.md](./phase-05-ai-and-alerts.md) | AI summaries, semantic triggers, Slack/Discord, digests |
| [phase-06-07-monetization-enterprise.md](./phase-06-07-monetization-enterprise.md) | Plans, webhooks, API keys, RBAC |

Related: auth modes ([../auth-modes.md](../auth-modes.md)), architecture
decisions ([../adrs/](../adrs/)).
