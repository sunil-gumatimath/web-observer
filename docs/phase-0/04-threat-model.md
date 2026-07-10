# Threat Model — SSRF & Tenant Isolation

Status: **Approved for Phase 1 implementation**  
Scope: MVP public monitoring

## Assets

| Asset | Impact if compromised |
|-------|------------------------|
| Workspace data (monitors, runs, diffs) | Cross-tenant leak |
| Raw HTML snapshots | Sensitive public content aggregation / abuse |
| Worker egress | Internal network access via SSRF |
| Notification channels | Spam / phishing via our mail domain |
| Credentials / secrets | Full system compromise |

## Trust boundaries

1. Browser / Clerk → API  
2. API → PostgreSQL / Redis / R2  
3. Workers → **arbitrary public internet** (highest risk)  
4. Workers → DB / R2 / Resend  

## STRIDE-style risks (priority)

### 1. SSRF via user-supplied URLs (Critical)

**Threat:** Attacker points monitor URL at `169.254.169.254`, localhost, internal VPC, or DNS-rebinding target.

**Mitigations (required Phase 1):**

- Allow only `http` / `https`  
- Reject embedded credentials in URLs  
- Reject malformed / ambiguous URLs  
- Safe IDN handling  
- Block loopback, private, link-local, multicast, reserved  
- Block cloud metadata endpoints  
- Validate **all** DNS results (A/AAAA)  
- Re-validate destination after **every** redirect  
- Redirect count limit  
- DNS rebinding defenses (pin resolved IP for request where possible)  
- Restrict egress network where possible  
- Same controls for future webhook destinations  

**Tests:** unit + integration suite for IPv4/IPv6, redirects, metadata hosts, rebinding cases.

### 2. Cross-workspace access (Critical)

**Threat:** IDOR on monitor/run/snapshot by guessing UUIDs or missing filters.

**Mitigations:**

- Every query scoped by `workspace_id` from membership  
- No reliance on security-through-obscurity of UUIDs alone  
- Signed short-lived URLs for R2 objects  
- Tenant isolation automated tests  

### 3. XSS via stored HTML / diffs (High)

**Threat:** Malicious page content rendered unsafely in dashboard.

**Mitigations:**

- Never directly render downloaded HTML in app chrome  
- Sanitize diff output before display  
- Future HTML preview only in sandboxed iframe, scripts disabled  

### 4. Resource exhaustion (High)

**Threat:** Huge responses, tight schedules, many monitors, slowloris targets.

**Mitigations:**

- Timeouts (connect, read, total)  
- Max response / decompressed size  
- Content-type allowlist  
- Per-domain concurrency and rate  
- Global worker concurrency  
- Workspace quotas (monitors, checks/day, storage)  
- Min check interval  

### 5. Duplicate alerts / replay (Medium)

**Threat:** Worker retry creates duplicate change events or emails.

**Mitigations:**

- Idempotency keys on runs and outbox  
- Single DB transaction for change + outbox  
- One active run per monitor  

### 6. Abuse of monitoring as open proxy / scanner (Medium)

**Threat:** Service used to harass third parties or probe networks.

**Mitigations:**

- Public pages only  
- robots.txt respect (RFC 9309) + honest User-Agent with contact  
- Back off on 429 / repeated 403  
- Domain owner contact / block path  
- Quotas and admin kill-switch  

### 7. Secrets leakage in logs (Medium)

**Threat:** Auth headers, cookies, page secrets in logs/Sentry.

**Mitigations:**

- Never log credentials or sensitive headers  
- Redact page content from default logs  
- Correlation IDs only (workspace, monitor, run, etc.)  

## Out of scope for MVP (accepted residual risk)

- Authenticated page monitoring (deferred with credential encryption design)  
- CAPTCHA / bot-defense bypass (will not implement)  
- Full legal clearance for every jurisdiction (document policy; user responsibility for targets)  

## Security requirements checklist (Phase 1 exit)

- [ ] SSRF suite green  
- [ ] No private/metadata IP access in tests  
- [ ] Workspace isolation tests green  
- [ ] Diff rendering safe (no raw HTML inject)  
- [ ] Secrets not in logs  
- [ ] Quotas enforced at API and worker edges  
