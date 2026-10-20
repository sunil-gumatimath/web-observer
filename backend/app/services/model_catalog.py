"""Model catalog for the LLM providers this app supports.

Single source of truth for the model picker in the UI and for the server-side
defaults. Every entry was verified live against the provider's OpenAI-compatible
``/chat/completions`` endpoint with the app's real summarisation prompt
(system prompt + ``<untrusted_*>`` fences + strict JSON output) at the app's
default 200-output-token cap.

Two things decide whether a model is usable here:

* the provider is free (Kilo Gateway ``isFree`` / $0 pricing) or the workspace
  supplies its own paid key, and
* the model returns a *complete* JSON object inside the output budget. Most
  reasoning models spend the whole budget on hidden thinking tokens and return
  an empty or truncated body, which the app treats as a failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Kilo Gateway: models whose input/output pricing is $0.
KILO_BASE = "https://api.kilo.ai/api/gateway"

# Google Gemini: OpenAI-compatible endpoint.
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


@dataclass(frozen=True)
class ModelEntry:
    """One selectable model."""

    value: str
    label: str
    provider: str
    base: str
    #: Why the model is ranked where it is, and any caveat the user needs.
    note: str = ""
    #: Output-token budget the model was measured to need, or None when the
    #: model never produced a complete reply. 200 means it fits the app's
    #: default cap; higher values are applied only to this model so reasoning
    #: models get room without inflating every other request.
    verified_at: int | None = None

    @property
    def verified_200(self) -> bool:
        """True when the model completes the task inside the default cap."""
        return self.verified_at == 200

    @property
    def usable(self) -> bool:
        """True when the model produced a complete reply at any measured cap."""
        return self.verified_at is not None


@dataclass(frozen=True)
class Provider:
    """A provider (base URL) and the models it offers."""

    id: str
    label: str
    base: str
    models: list[ModelEntry] = field(default_factory=list)
    #: True when every model on this provider is free to use.
    free: bool = True


# ---------------------------------------------------------------------------
# Kilo Gateway — free models ($0 input/output).
#
# Ordering is a Jev (jev-1.13.0) ranking pass over the live free set, scored
# against this app's job: a short, factual, strictly-JSON diff summary. The
# ranking was grounded in live probes of every model, not in model descriptions.
#
# ``verified_at`` comes from ``scripts/probe_free_models.py``, which runs the
# real summary prompt through the real request path. 200 = fits the app's
# default cap; 800 = passes once its own cap is applied; None = no complete
# reply observed (or the probe was rate-limited and never got a clean run).
# ---------------------------------------------------------------------------
_KILO_MODELS: list[ModelEntry] = [
    ModelEntry(
        value="poolside/laguna-s-2.1:free",
        label="Laguna S 2.1 (free) — Poolside · Coding · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Complete JSON at the app's 200-token cap. Best verified free pick.",
        verified_at=200,
    ),
    ModelEntry(
        value="cohere/north-mini-code:free",
        label="North Mini Code (free) — Cohere · Coding · 256K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Complete JSON at the app's 200-token cap.",
        verified_at=200,
    ),
    ModelEntry(
        value="minimax/minimax-m3.1-flash:free",
        label="MiniMax M3.1 Flash (free) — MiniMax · Multimodal · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Complete JSON at the app's 200-token cap.",
        verified_at=200,
    ),
    ModelEntry(
        value="nvidia/nemotron-3-ultra-550b-a55b:free",
        label="Nemotron 3 Ultra (free) — NVIDIA · 550B · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Complete JSON at the app's 200-token cap.",
        verified_at=200,
    ),
    ModelEntry(
        value="xingchen-agi/xing4.0-29b-a4b:free",
        label="Xing4.0 29B A4B (free) — XingChen · Reasoning · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Complete JSON at the app's 200-token cap.",
        verified_at=200,
    ),
    ModelEntry(
        value="openrouter/free",
        label="Free Models Router — OpenRouter · Vision · 200K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Router over free models; completed at 200 tokens but reliability varies.",
        verified_at=200,
    ),
    ModelEntry(
        value="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        label="Nemotron 3 Nano Omni (free) — NVIDIA · Multimodal · 256K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Complete JSON at the app's 200-token cap (rate-limited in the 2026-10 re-probe).",
        verified_at=200,
    ),
    ModelEntry(
        value="poolside/laguna-xs-2.1:free",
        label="Laguna XS 2.1 (free) — Poolside · Coding · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Complete JSON at the app's 200-token cap (rate-limited in the 2026-10 re-probe).",
        verified_at=200,
    ),
    ModelEntry(
        value="nvidia/nemotron-3.5-super-vl:free",
        label="Nemotron 3.5 Super VL (free) — NVIDIA · Vision · Video · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: complete JSON at an 800-token cap.",
        verified_at=800,
    ),
    ModelEntry(
        value="reflection/beam-free",
        label="Beam 1.0 (free) — Reflection · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: complete JSON at an 800-token cap.",
        verified_at=800,
    ),
    ModelEntry(
        value="stealth/glyph-cluster",
        label="Glyph Cluster (free) — Stealth · 256K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: complete JSON at an 800-token cap, but slow (~20s).",
        verified_at=800,
    ),
    ModelEntry(
        value="liquid/lfm-2.5-2.6b:free",
        label="LFM2.5-2.6B (free) — Liquid AI · Lightweight · 65K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning is mandatory; complete JSON at an 800-token cap.",
        verified_at=800,
    ),
    ModelEntry(
        value="nvidia/nemotron-3-super-120b-a12b:free",
        label="Nemotron 3 Super (free) — NVIDIA · 120B · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: no complete reply at 200 or 800 tokens.",
    ),
    ModelEntry(
        value="nvidia/nemotron-3.5-lightning:free",
        label="Nemotron 3.5 Lightning (free) — NVIDIA · Reasoning · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: returned empty content at an 800-token cap.",
    ),
    ModelEntry(
        value="dots-studio/dots-3-note-preview:free",
        label="Dots3-Note Preview (free) — Dots Studio · Vision · 512K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: no complete reply at an 800-token cap.",
    ),
    ModelEntry(
        value="kilo-auto/free",
        label="Auto Free — Kilo · Server default router · 256K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Rotates across free models; timed out at a 200-token cap.",
    ),
    ModelEntry(
        value="thinkingmachines/inkling-small:free",
        label="Inkling Small (free) — Thinking Machines · Multimodal · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model; hit its daily request limit during the probe.",
    ),
    ModelEntry(
        value="nvidia/nemotron-3.5-content-safety:free",
        label="Nemotron 3.5 Content Safety (free) — NVIDIA · Moderation · 128K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Moderation model, not a summariser.",
    ),
]

# ---------------------------------------------------------------------------
# Google Gemini — paid tier, used with a workspace's own API key.
# ---------------------------------------------------------------------------
_GEMINI_MODELS: list[ModelEntry] = [
    ModelEntry(
        value="gemini-3.1-flash-lite",
        label="Gemini 3.1 Flash-Lite — Google · 1M ctx",
        provider="gemini",
        base=GEMINI_BASE,
        note="Complete JSON at the app's 200-token cap.",
        verified_at=200,
    ),
    ModelEntry(
        value="gemini-3.5-flash-lite",
        label="Gemini 3.5 Flash-Lite — Google · 1M ctx",
        provider="gemini",
        base=GEMINI_BASE,
        note="Complete JSON at the app's 200-token cap.",
        verified_at=200,
    ),
    ModelEntry(
        value="gemini-flash-lite-latest",
        label="Gemini Flash-Lite Latest — Google · 1M ctx",
        provider="gemini",
        base=GEMINI_BASE,
        note="Complete JSON at the app's 200-token cap.",
        verified_at=200,
    ),
    ModelEntry(
        value="gemini-3.5-flash",
        label="Gemini 3.5 Flash — Google · 1M ctx",
        provider="gemini",
        base=GEMINI_BASE,
        note="Reasoning model: needs a larger output cap than 200 tokens.",
    ),
    ModelEntry(
        value="gemini-3.8-flash",
        label="Gemini 3.8 Flash — Google · 1M ctx",
        provider="gemini",
        base=GEMINI_BASE,
        note="Reasoning model: needs a larger output cap than 200 tokens.",
    ),
    ModelEntry(
        value="gemini-3.6-flash",
        label="Gemini 3.6 Flash — Google · 1M ctx",
        provider="gemini",
        base=GEMINI_BASE,
        note="Reasoning model: needs a larger output cap than 200 tokens.",
    ),
    ModelEntry(
        value="gemini-3.7-flash",
        label="Gemini 3.7 Flash — Google · 1M ctx",
        provider="gemini",
        base=GEMINI_BASE,
        note="Reasoning model: needs a larger output cap than 200 tokens.",
    ),
    ModelEntry(
        value="gemini-3.1-pro-preview",
        label="Gemini 3.1 Pro Preview — Google · 1M ctx",
        provider="gemini",
        base=GEMINI_BASE,
        note="Pro tier: needs a paid quota.",
    ),
]

PROVIDERS: list[Provider] = [
    Provider(
        id="kilo",
        label="Kilo Gateway (free models)",
        base=KILO_BASE,
        models=_KILO_MODELS,
        free=True,
    ),
    Provider(
        id="gemini",
        label="Google Gemini (your own API key)",
        base=GEMINI_BASE,
        models=_GEMINI_MODELS,
        free=False,
    ),
]

#: Base URL -> provider id, so a stored base can be matched to its catalog.
PROVIDER_BY_BASE: dict[str, str] = {p.base: p.id for p in PROVIDERS}


#: Models that must not be used as a failover candidate for a given base:
#: they are either cross-provider or unusable at the app's output cap.
def candidates_for_base(base: str | None, *, verified_only: bool = False) -> list[str]:
    """Ordered failover models for a provider base.

    Only models from the same provider are eligible — a Kilo model id sent to
    Google (or vice versa) 404s. When the base is unknown, the primary alone
    is used, matching the previous behaviour of never guessing a provider.

    ``verified_only`` drops models that never produced a complete reply at any
    measured cap. Every failover attempt is still a real request against the
    provider's quota, so trying a reasoning model that is known to spend the
    budget on hidden thinking burns quota and returns nothing. The default
    failover chain asks for verified models only, while an explicit user list
    is validated against the full catalog so that a deliberate choice is never
    silently dropped.
    """
    provider_id = PROVIDER_BY_BASE.get((base or "").strip().rstrip("/"))
    if not provider_id:
        return []
    provider = next(p for p in PROVIDERS if p.id == provider_id)
    return [m.value for m in provider.models if m.usable or not verified_only]


def output_cap_for(base: str | None, model: str | None, default: int) -> int:
    """Output-token budget to use for one model.

    Models measured to need more room than the default get their own cap, so a
    reasoning model can finish its JSON without inflating every other request.
    Unknown models and unverified ones keep the caller's default.
    """
    provider = provider_for_base(base)
    if provider is None:
        return default
    for entry in provider.models:
        if entry.value == (model or "").strip() and entry.usable:
            return max(default, entry.verified_at or 0)
    return default


def provider_for_base(base: str | None) -> Provider | None:
    """The provider that serves ``base``, or None for an unknown base."""
    provider_id = PROVIDER_BY_BASE.get((base or "").strip().rstrip("/"))
    if not provider_id:
        return None
    return next(p for p in PROVIDERS if p.id == provider_id)
