# Documentation

Index of Web Observer docs. Start with the root [README](../README.md) for the
project overview and quickstart.

## Getting started

| Doc | Topic |
| ----- | ------- |
| [local-dev.md](./local-dev.md) | Run the stack locally + operations reference (processes, secrets, retention, metrics, service targets) |

## Guides

| Doc | Topic |
| ----- | ------- |
| [guides/clerk.md](./guides/clerk.md) | Clerk auth (dev setup + production hardening) |
| [guides/resend-setup.md](./guides/resend-setup.md) | Email alerts (Resend) |
| [guides/cloudflare-free-features.md](./guides/cloudflare-free-features.md) | Cloudflare free tier end-to-end (R2, screenshots CDN, Tunnel, Browser Rendering failover, URL Scanner, Workers, Web Analytics) |
| [guides/monitoring-modes.md](./guides/monitoring-modes.md) | The 9 monitoring modes, their options and their limits |
| [integrations/n8n-zapier.md](./integrations/n8n-zapier.md) | n8n / Zapier automation |

## Reference

| Doc | Topic |
| ----- | ------- |
| [architecture.md](./architecture.md) | Component, module, ERD, and sequence diagrams |
| [auth-modes.md](./auth-modes.md) | Dev-token vs Clerk authentication |
| [roadmap.md](./roadmap.md) | Feature roadmap (Phases 8–10) |
| [security/threat-model.md](./security/threat-model.md) | Security policy: SSRF, tenant isolation, out-of-scope rules |

## Operations

| Doc | Topic |
| ----- | ------- |
| [../scripts/](../scripts/) | Stack restart/stop scripts for Windows and Linux/WSL |
| [../workers/](../workers/) | Cloudflare Workers: Browser Rendering failover, share-page edge cache |

## Decisions

[adrs/007-stealth-evasion-policy.md](./adrs/007-stealth-evasion-policy.md) — stealth-evasion policy (Proposed; see also [security/threat-model.md](./security/threat-model.md)).
