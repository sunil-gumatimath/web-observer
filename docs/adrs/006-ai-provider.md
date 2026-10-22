# ADR 006: AI Summaries Provider

Covers the AI-provider decision and the original "keep AI out of core
detection" decision (formerly ADR 005, merged in 2026-10-22).

ADR 005 deferred AI to a later phase: *"a later phase may summarize diffs,
classify changes, or help generate ignore rules."* This ADR is that later
phase — Phase 5 shipped.

## Status

Accepted (Phase 5)

## Context

We want optional human-readable summaries and change classification. Detection must remain deterministic (hash/diff).

AI summaries are valuable but non-deterministic, costly, and risky if used as the sole change detector.

## Decision

1. **Detection is never AI-dependent.** Hash/diff pipeline always produces change events first.  
2. **AI is not part of core change detection.** Detection remains: extract → normalize → hash → text diff.  
3. Summaries are **optional**, size-limited, and fail-open (deterministic summary remains).  
4. Provider: **OpenAI-compatible HTTP API** (`LLM_API_BASE` + `LLM_API_KEY` + `LLM_MODEL`).  
5. If no API key: use **heuristic classifier + template summary** (no external call).  
6. Treat page/diff content as **untrusted**; never put secrets in prompts; cap tokens/chars.  
7. Track usage in logs / usage counters later (`ai_tokens` optional).  
8. The provider is chosen against cost, privacy, retention, and quality — and the choice is recorded here, not left implicit.

## Safety

- System instructions separate from user/diff content.  
- Max diff chars into model (default 6k).  
- Never suppress change alerts solely based on AI.  
- Noise feedback is user-driven, not auto-suppressed by AI.

### Safety constraints carried over from ADR 005

These apply whenever AI is added to the pipeline:

- Page content is untrusted input.  
- Deterministic alerts if AI is unavailable.  
- Never use AI as the only change detector.  
- Never silently suppress critical changes based only on AI.

## Consequences

- Works offline/dev without LLM.  
- Easy swap of providers (OpenAI, Azure, Groq, local).  
- Cleaner MVP with lower false-confidence risk.  
- AI cost is optional and metered later.

## Supersede note (2026-09)

Original §Safety stated noise feedback is user-driven, not
auto-suppressed, and alerts are never suppressed solely on AI. Current
behavior (§3.3 roadmap): `semantic_trigger` + watch-note
triage may mark `is_noise=true` automatically via LLM, with
guardrails — `<untrusted_diff_content>` fences, size caps, fail-open
on LLM error, noise retained in inbox (not deleted), excluded from
notifications/digests.  
