# ADR 007: Stealth-Evasion Policy

## Status

Proposed

## Context

Threat model (`docs/phases/phase-00-threat-model.md`) states CAPTCHA /
bot-defense bypass "will not implement", while roadmap §5.2 proposes
stealth evasion for Cloudflare Turnstile, DataDome, and Akamai. This
is a direct policy contradiction that must be resolved explicitly.

## Decision

No stealth-evasion implementation until explicit approval covering:
legal review, target-site ToS assessment, and abuse controls.

## Options Considered

- **Status quo (no evasion):** respect bot defenses, back off on
  429/403, keep honest User-Agent. Lowest legal/abuse risk.
- **Passive hardening only:** realistic headers, viewport jitter, no
  fingerprint spoofing. Still detectable; marginal benefit.
- **Full stealth (deferred):** `playwright-stealth`-style fingerprint
  masking, humanized input. Requires approval above.

## Residual Risk

Even passive measures may violate some sites' ToS; per-domain
opt-in, robots.txt respect, and kill-switch remain required.

## Consequences

- Roadmap §5.2 stays Proposed-only; threat model prohibition stands.
- Any future stealth work needs a new ADR superseding this one.
- Proxy support (§5.1, user-supplied URIs) is unaffected by this ADR.
