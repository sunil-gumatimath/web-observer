# ADR 005: AI Deferred from Core Detection

## Status

Accepted

## Context

AI summaries are valuable but non-deterministic, costly, and risky if used as the sole change detector.

## Decision

- AI is **not** part of core change detection.  
- Detection remains: extract → normalize → hash → text diff.  
- A later phase may summarize diffs, classify changes, or help generate ignore rules.  
- Provider chosen via ADR before AI phase (cost, privacy, retention, quality).

## Safety constraints (when added)

- Page content is untrusted input.  
- Deterministic alerts if AI is unavailable.  
- Never use AI as the only change detector.  
- Never silently suppress critical changes based only on AI.

## Consequences

- Cleaner MVP.  
- Lower false-confidence risk.  
- AI cost is optional and metered later.
