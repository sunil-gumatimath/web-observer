# Documentation

Index of Web Observer docs. Start with the root [README](../README.md) for the
project overview and quickstart.

## Getting started

| Doc | Topic |
| ----- | ------- |
| [local-dev.md](./local-dev.md) | Run the stack locally (native processes) |
| [operations/local-setup-and-ops.md](./operations/local-setup-and-ops.md) | Process topology, secrets, retention |

## Guides

| Doc | Topic |
| ----- | ------- |
| [guides/clerk-setup.md](./guides/clerk-setup.md) | Clerk auth (dev) |
| [guides/clerk-production.md](./guides/clerk-production.md) | Clerk production hardening |
| [guides/resend-setup.md](./guides/resend-setup.md) | Email alerts (Resend) |
| [guides/r2-setup.md](./guides/r2-setup.md) | Cloudflare R2 snapshot storage |
| [guides/cloudflare-free-features.md](./guides/cloudflare-free-features.md) | Cloudflare free tier end-to-end (R2, screenshots CDN, Tunnel, Browser Rendering failover, URL Scanner, Workers) |
| [guides/web-analytics.md](./guides/web-analytics.md) | Cookie-less Cloudflare Web Analytics beacon |
| [guides/monitoring-modes.md](./guides/monitoring-modes.md) | The 9 monitoring modes, their options and their limits |
| [integrations/n8n-zapier.md](./integrations/n8n-zapier.md) | n8n / Zapier automation |

## Reference

| Doc | Topic |
| ----- | ------- |
| [architecture.md](./architecture.md) | Component, module, ERD, and sequence diagrams |
| [auth-modes.md](./auth-modes.md) | Dev-token vs Clerk authentication |
| [roadmap.md](./roadmap.md) | Feature roadmap (Phases 8–10) |

## Operations

| Doc | Topic |
| ----- | ------- |
| [operations/local-setup-and-ops.md](./operations/local-setup-and-ops.md) | Process topology, secrets, retention, metrics |
| [../scripts/](../scripts/) | `restart-stack.ps1`, `stop-stack.ps1`, `cloudflare-tunnel.ps1`, `smoke.sh` |
| [../workers/](../workers/) | Cloudflare Workers: Browser Rendering failover, share-page edge cache |

## Decisions

[adrs/](./adrs/) — architecture decision records (ADR 001–007).

## Phase records

[phases/](./phases/) — historical phase docs (Phase 0 discovery through Phase 7).
