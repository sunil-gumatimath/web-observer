# ADR 004: Snapshot Storage and Email

## Status

Accepted

## Context

Raw HTML (and later screenshots) can be large. Alerts must be reliable transactional email.

## Decision

- **Cloudflare R2** for raw snapshots (and later screenshots).  
  - Workspace-scoped paths, non-guessable IDs, signed URLs, lifecycle retention.  
- **PostgreSQL** for metadata, hashes, run state, and normalized content where appropriate.  
- **Resend** for MVP email via transactional **notification outbox**.

## Consequences

- Keep large blobs out of Postgres.  
- Email delivery is async and retryable.  
- Local/dev can use the filesystem (`STORAGE_BACKEND=local`) or any S3-compatible endpoint behind the same interface.
