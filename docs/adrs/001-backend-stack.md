# ADR 001: Backend Stack

## Status

Accepted

## Context

We need a backend for multi-tenant monitor CRUD, scheduled checks, secure fetching, hashing/diffs, and notifications.

## Decision

- Language: **Python 3.12+**
- API: **FastAPI** + **Pydantic** + **OpenAPI**
- ORM: **SQLAlchemy 2.x**
- Migrations: **Alembic**
- DB: **PostgreSQL 16**
- Queue: **Redis** + **Dramatiq**
- HTTP client: **httpx**
- HTML/CSS: **selectolax**
- Tests: **pytest**

## Consequences

- Strong fit for scraping, workers, and later Playwright.
- Two runtimes with Next.js frontend (accepted).
- OpenAPI enables typed frontend clients.
