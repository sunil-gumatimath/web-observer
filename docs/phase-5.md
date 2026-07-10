# Phase 5 — AI Summaries & Alert Expansion

## Features

| Feature | Behavior |
|---------|----------|
| **AI summary** | After deterministic change; never detects alone |
| **Category** | pricing, availability, legal, content, design, api, other |
| **Heuristic** | Always available without API keys |
| **LLM** | Optional OpenAI-compatible chat completions |
| **Slack / Discord** | Webhook channels (`type=slack\|discord`) |
| **Digest** | daily / weekly workspace digests via `digest` service |
| **Noise feedback** | `POST .../changes/{id}/noise` excludes from digests |

## Env

```env
AI_SUMMARIES_ENABLED=true
LLM_API_KEY=           # empty => heuristic only
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
AI_MAX_DIFF_CHARS=6000
```

## ADR

See `docs/adrs/006-ai-provider.md`.

## Safety

- Diff treated as untrusted input  
- Size-capped prompts  
- Fail-open to heuristic if LLM fails  
- AI never suppresses change events  

## Migration

`alembic upgrade head` → revision `003`
