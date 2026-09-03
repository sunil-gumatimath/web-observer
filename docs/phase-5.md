<p align="center">
  <img src="../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Phase 5 — AI Summaries & Alert Expansion

## Features

| Feature | Behavior |
|---------|----------|
| **AI summary** | After deterministic change; never detects alone |
| **Category** | pricing, availability, legal, content, design, api, other |
| **Title & Impact** | Short title + severity (`critical`, `high`, `medium`, `low`) + confidence (`0.0–1.0`) stored as first-class DB columns on `ChangeEvent` |
| **Semantic Triggers** | Plain-English alert rules (`semantic_trigger` on `Monitor`); filters non-matching diffs as noise |
| **Distributed Dedup** | Redis-backed TTL cache (`ai_dedup:<hash>`) with process-memory fallback to avoid redundant LLM invocations |
| **AI Executive Digest** | Batch synthesis briefing included in daily / weekly workspace digests |
| **Heuristic** | Always available without API keys |
| **LLM** | Optional OpenAI-compatible chat completions (default `LLM_API_BASE=https://api.kilo.ai/api/gateway`, `LLM_MODEL=minimax/minimax-m3:free`; `LLM_FALLBACK_MODELS` tried in order, empty disables failover) |
| **Slack / Discord** | Webhook channels (`type=slack\|discord`) |
| **Digest** | daily / weekly workspace digests via `digest` service |
| **Noise feedback** | `POST .../changes/{id}/noise` excludes from notifications & digests |

## Env

```env
AI_SUMMARIES_ENABLED=true
LLM_API_KEY=           # empty => heuristic only
LLM_API_BASE=https://api.kilo.ai/api/gateway
LLM_MODEL=minimax/minimax-m3:free
LLM_FALLBACK_MODELS=minimax/minimax-m3:free,nvidia/nemotron-3-super:free,google/gemma-4-26b-a4b:free,meta-llama/llama-3.3-70b-instruct:free
AI_MAX_DIFF_CHARS=6000
AI_MAX_OUTPUT_TOKENS=200
AI_ASYNC_ENRICHMENT=false   # true => heuristic row now, LLM upgrade in ai_enrich worker
AI_DEDUP_TTL_SECONDS=600    # Redis ai_dedup:<hash> TTL, process-memory fallback
REDIS_URL=redis://localhost:6379/0
```

## ADR

See `docs/adrs/006-ai-provider.md`.

## Safety & Hardening

- **Prompt Injection Defense:** Diffs enclosed in `<untrusted_diff_content>...</untrusted_diff_content>` XML fences; system prompt explicitly instructed to ignore overrides inside diff text.
- **Token Bounds:** Size-capped prompts (`AI_MAX_DIFF_CHARS`) and strict `max_tokens` limits.
- **Fail-open Resilience:** Automatic fallback to heuristics if LLM times out or errors.
- **Noise Non-Destruction:** Suppressed changes are marked `is_noise=true` for transparency in the Alerts inbox, never silently discarded.

## Migration

`alembic upgrade head` → revision `012_add_ai_intelligence_fields` (adds `title`, `impact`, `confidence` to `change_events` and `semantic_trigger` to `monitors`).
