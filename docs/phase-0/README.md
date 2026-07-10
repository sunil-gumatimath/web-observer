# Phase 0 — Validation and Architecture

## Exit criteria

| Criterion | Status |
|-----------|--------|
| No unresolved MVP technology choices | **Met** (see `docs/adrs/`) |
| Scheduler and retry behavior documented | **Met** (`02-architecture.md`, ADR 002) |
| Security requirements approved | **Met** (`04-threat-model.md`) |
| MVP user flow documented end to end | **Met** (`01-mvp-user-flow.md`) |

## Deliverables index

| Doc | Description |
|-----|-------------|
| [00-product-scope.md](./00-product-scope.md) | Vision, MVP scope, non-goals |
| [01-mvp-user-flow.md](./01-mvp-user-flow.md) | End-to-end user + system flow |
| [02-architecture.md](./02-architecture.md) | Diagrams, lifecycle, retries |
| [03-erd.md](./03-erd.md) | Core data model |
| [04-threat-model.md](./04-threat-model.md) | SSRF + tenant isolation |
| [05-api-outline.md](./05-api-outline.md) | REST outline |
| [06-backlog.md](./06-backlog.md) | Implementation backlog |
| [07-deployment-plan.md](./07-deployment-plan.md) | Local → beta deploy |
| [08-kpis-and-quotas.md](./08-kpis-and-quotas.md) | Metrics and limits |
| [../adrs/](../adrs/) | Architecture decision records |

## Ongoing product validation (not blocking engineering start)

- User interviews  
- Persona confirmation  
- Willingness to pay  

Engineering may proceed to **Phase 1** while product validation continues.

## Next

Start **Phase 1 — Internal Vertical Slice** (`docs/phase-0/06-backlog.md` § Phase 1).
