# Kilo free models for Web Observer

Checked: 2026-10-29. The live Kilo Gateway model-list endpoint and Kilo's current Free Models page were checked. Free promotions and availability can change.

## What the live catalog says

Kilo's official Gateway docs name `GET https://ai-gateway.kilo.ai/api/v1/models` as the unauthenticated model-list endpoint. Filtering its live response for `pricing.prompt == 0`, `pricing.completion == 0`, and text input plus text output returned 18 entries at the time checked. This includes model IDs intended for text chat as well as audio generation models, so a zero price alone does not mean a model fits this app's text-only chat-completion workflow.

The 18 IDs returned by that filter were: `kilo-auto/free`, `nvidia/nemotron-3.5-super-vl:free`, `reflection/beam-free`, `stealth/glyph-cluster`, `recursive/flint-v1.0:free`, `xingchen-agi/xing4.0-29b-a4b:free`, `dots-studio/dots-3-note-preview:free`, `liquid/lfm-2.5-2.6b:free`, `nvidia/nemotron-3.5-lightning:free`, `poolside/laguna-s-2.1:free`, `poolside/laguna-xs-2.1:free`, `cohere/north-mini-code:free`, `nvidia/nemotron-3.5-content-safety:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`, `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`, `google/lyria-3-pro-preview`, `google/lyria-3-clip-preview`, and `openrouter/free`. The two Lyria entries have text-plus-audio output in the endpoint metadata; the latter are audio-generation models and should not be treated as normal text summarizers just because the endpoint includes text output.

Kilo's public Free Models page currently highlights four active hosted free models: `nvidia/nemotron-3.5-super-vl:free`, `dots-studio/dots-3-note-preview:free`, `poolside/laguna-s-2.1:free`, and `nvidia/nemotron-3-ultra-550b-a55b:free`. The page says the catalog is freshness-sorted and explicitly reports no comparable tested overall winner in its promoted KiloBench section. Its “Recommended” Nemotron Super VL label is a Kilo model/catalog recommendation, not a benchmarked winner for Web Observer's short JSON summaries.

The Gateway API also reports `response_format` / `structured_outputs` support. This is a useful filter, but not proof that the provider actually returns complete JSON for Web Observer's prompt. Existing app-specific probes in `backend/app/services/model_catalog.py` report Laguna S as the only listed model to complete the real summary prompt within the default 200-token cap; several other models only finish at 800 tokens, and several known entries fail, return empty/truncated output, or are rate-limited. These observations are dated 2026-10-28 and should be refreshed with real probes before changing the recommendation.

## Recommendation and live app probes

The app was probed on 2026-10-29 with synthetic pricing changes against its actual combined summary/triage call, change Q&A function, and digest-style plain-text prompt. `poolside/laguna-s-2.1:free`, `nvidia/nemotron-3.5-super-vl:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`, and `reflection/beam-free` passed all three paths. Laguna was the best default: it passed all paths and is the only model in the app's prior prompt probes to complete strict summary JSON at the normal 200-token output cap.

The fifth Settings option is `dots-studio/dots-3-note-preview:free`: it produced a complete summary/triage result at the 800-token cap, but Q&A and digest calls returned HTTP 403 for the current Kilo key. Other candidates returned 403s or 429s during these checks. The UI shows this limitation in the model note; it is not recommended as the default. The four models that passed all three paths should be preferred when reliability matters.

Settings now shows a five-model shortlist with per-model probe notes and marks Laguna as recommended. The gateway list had 18 zero-priced entries with text input/output, but that includes audio-generation models and entries that are blocked or unreliable for this app. Exclude audio-generation-only choices from the text-chat picker. Do not choose Kilo Auto Free as the default for sensitive monitored page data without an explicit disclosure: Kilo documents that it may route to providers that log prompts and outputs, including NVIDIA free endpoints.

## Sources

- Kilo Gateway model-list endpoint documentation: <https://github.com/Kilo-Org/kilocode/blob/main/packages/kilo-docs/pages/gateway/models-and-providers.md> (lists `/api/v1/models`, pricing, context, and supported features; free availability changes).
- Kilo official Free Models page: <https://kilo.ai/landing/free-models> (four highlighted active free models, zero-cost criteria, catalog freshness, no current comparable tested winner, Auto Free data-handling note).
- Kilo official free-usage guide: <https://github.com/Kilo-Org/kilocode/blob/main/packages/kilo-docs/pages/getting-started/using-kilo-for-free.md> (Auto Free routing, individual free model selection, upstream rate limits and provider logging cautions).
- App-specific model probes and catalog snapshot: `backend/app/services/model_catalog.py` (updated 2026-10-28; use as dated app evidence, not as Kilo's live availability source).
