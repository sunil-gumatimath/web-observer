# ADR 003: Authentication Provider

## Status

Accepted (MVP)

## Context

MVP needs sign-in and workspace membership without building custom JWT/session infrastructure.

## Decision

- **Clerk** for authentication.  
- FastAPI verifies Clerk-issued tokens.  
- Authorization is **workspace membership** (`workspace_id` on every owned query).  
- No custom JWT auth for MVP.

## Revisit when

Pricing, compliance, or regional availability requires self-hosted or alternative IdP. Document any switch in a new ADR.

## Consequences

- Faster Phase 2 dashboard.  
- Vendor dependency and cost.  
- Phase 1 can use internal/dev auth bypass or seed users until Clerk is wired.
