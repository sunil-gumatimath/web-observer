# ADR 006: AI Summaries Provider

## Status

Accepted (Phase 5)

## Context

We want optional human-readable summaries and change classification. Detection must remain deterministic (hash/diff).

## Decision

1. **Detection is never AI-dependent.** Hash/diff pipeline always produces change events first.  
2. Summaries are **optional**, size-limited, and fail-open (deterministic summary remains).  
3. Provider: **OpenAI-compatible HTTP API** (`LLM_API_BASE` + `LLM_API_KEY` + `LLM_MODEL`).  
4. If no API key: use **heuristic classifier + template summary** (no external call).  
5. Treat page/diff content as **untrusted**; never put secrets in prompts; cap tokens/chars.  
6. Track usage in logs / usage counters later (`ai_tokens` optional).

## Safety

- System instructions separate from user/diff content.  
- Max diff chars into model (default 6k).  
- Never suppress change alerts solely based on AI.  
- Noise feedback is user-driven, not auto-suppressed by AI.

## Consequences

- Works offline/dev without LLM.  
- Easy swap of providers (OpenAI, Azure, Groq, local).  
