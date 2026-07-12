# Product Scope — Phase 0

Status: **Approved for MVP implementation**  
Source: `Web Observer-final-roadmap.md`  
Date: 2026-07-10

## Product vision

Web Observer detects changes on public web pages (or selected sections) and sends high-signal alerts with clear before-and-after text diffs.

> Tell me when the web pages I care about change and clearly explain what changed.

## Initial personas

| Persona | Example use |
|---------|-------------|
| Developer / eng team | Docs, changelogs, release notes |
| Product / founder | Competitor pricing, feature lists |
| Researcher | Public notices, tenders, job boards |

## Highest-value first use case

**Competitive and product page text changes** (pricing, features, docs) with email alerts and readable diffs.

Assumption to validate in beta: users will pay for reliable, low-noise checks more than for AI summaries or visual diffs.

## MVP in scope

- Public HTTP/HTTPS pages only
- Whole-page normalized text monitoring
- CSS-selector partial-page monitoring
- Configurable schedules (with minimum interval)
- Deterministic extraction + normalization + content hash
- Before-and-after text diffs
- Email alerts (Resend)
- Monitor run history and failure diagnostics
- Workspace-scoped web dashboard (Phase 2 UI; Phase 1 may use CLI/admin)
- Manual and scheduled checks

## MVP non-goals (explicitly deferred)

- XPath
- Authenticated / private pages
- CAPTCHA, paywall, login, bot-defense bypass
- JSON/API field monitoring
- List / collection monitoring
- Visual comparison
- AI summaries
- Slack, Discord, SMS
- Bulk imports
- Deep crawling
- Enterprise (SSO, RBAC, audit exports)

## MVP completion definition

A private-beta user can:

1. Sign in  
2. Create or join a workspace  
3. Create whole-page or CSS-selector monitor  
4. Choose an allowed schedule  
5. See first successful baseline (no change alert)  
6. Receive email when content changes  
7. Open secure before-and-after diff  
8. Inspect successful and failed runs  
9. Pause, resume, update, or delete monitor  
10. Delete associated snapshots and history  

Plus: workspace isolation, SSRF protection, idempotent retries, no duplicate alerts on retry, quota enforcement, secure snapshot access, DB backup/restore, operational visibility.

## Beta success targets (summary)

- ≥99% successful eligible checks  
- ≥95% lightweight checks complete within 15s  
- ≥99% checks start within 5 minutes of schedule  
- <1 duplicate notification per 10,000 deliveries  
- ≥90% rated alerts considered useful  
- Zero cross-workspace access incidents  
- Zero successful SSRF to blocked destinations  
- ≥30% four-week workspace retention in beta  

See `08-kpis-and-quotas.md` for full metrics and quota defaults.
