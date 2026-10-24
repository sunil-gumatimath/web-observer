"""Model catalog for the LLM providers this app supports.

Single source of truth for the model picker in the UI and for the server-side
defaults. Probe status is tracked per entry; a model is marked verified only
when it produces a complete response to the app's real summarisation prompt
(system prompt + ``<untrusted_*>`` fences + strict JSON output) within its
measured output-token budget.

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
# Set taken from the live ``/api/gateway/models`` payload (``isFree=true``) on
# 2026-10-23. Ordering is a Jev (jev-1.14.0) ranking pass over that live set,
# scored against this app's job: a short, factual, strictly-JSON diff summary.
# The ranking was grounded in clean live probes of every model (no failover, no
# dedup) with the app's real prompt, not in model descriptions.
#
# ``verified_at`` comes from those probes. 200 = fits the app's default cap;
# 800 = passes once its own cap is applied; None = no complete reply observed
# (reasoning burned the budget, the model returned non-JSON, timed out, was
# rate-limited, or was not served).
# ---------------------------------------------------------------------------
_KILO_MODELS: list[ModelEntry] = [
    ModelEntry(
        value="poolside/laguna-s-2.1:free",
        label="Laguna S 2.1 (free) — Poolside · Coding · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Jev #1. Complete JSON at the 200-token cap in 3/3 clean probes (3-6s).",
        verified_at=200,
    ),
    ModelEntry(
        value="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        label="Nemotron 3 Nano Omni (free) — NVIDIA · Multimodal · 256K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Jev #2. Complete JSON at the 200-token cap in 3/3 clean probes (2-5s).",
        verified_at=200,
    ),
    ModelEntry(
        value="cohere/north-mini-code:free",
        label="North Mini Code (free) — Cohere · Coding · 256K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Jev #3. Complete JSON at the 200-token cap in 3/3 clean probes (2-6s); one earlier app-path run truncated.",
        verified_at=200,
    ),
    ModelEntry(
        value="xingchen-agi/xing4.0-29b-a4b:free",
        label="Xing4.0 29B A4B (free) — XingChen · Reasoning · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Complete JSON at 200 tokens once, but repeated free-tier HTTP 429s afterwards; treat as rate-limited.",
        verified_at=200,
    ),
    ModelEntry(
        value="nvidia/nemotron-3.5-super-vl:free",
        label="Nemotron 3.5 Super VL (free) — NVIDIA · Vision · Video · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: complete JSON at an 800-token cap (12.5s).",
        verified_at=800,
    ),
    ModelEntry(
        value="dots-studio/dots-3-note-preview:free",
        label="Dots3-Note Preview (free) — Dots Studio · Vision · 512K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: complete JSON at an 800-token cap (8.7s).",
        verified_at=800,
    ),
    ModelEntry(
        value="recursive/flint-v1.0:free",
        label="Flint v1.0 (free) — Recursive · Coding · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: complete JSON at an 800-token cap (4.9s).",
        verified_at=800,
    ),
    ModelEntry(
        value="reflection/beam-free",
        label="Beam 1.0 (free) — Reflection · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: complete JSON at an 800-token cap (3.1s).",
        verified_at=800,
    ),
    ModelEntry(
        value="nvidia/nemotron-3-ultra-550b-a55b:free",
        label="Nemotron 3 Ultra (free) — NVIDIA · 550B · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: complete JSON at an 800-token cap (9.5s).",
        verified_at=800,
    ),
    ModelEntry(
        value="liquid/lfm-2.5-2.6b:free",
        label="LFM2.5-2.6B (free) — Liquid AI · Lightweight · 65K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning is mandatory; complete JSON at an 800-token cap but ~55s.",
        verified_at=800,
    ),
    ModelEntry(
        value="kilo-auto/free",
        label="Auto Free — Kilo · Server default router · 256K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Router over free models; complete JSON at an 800-token cap (2.7s), empty at 200.",
        verified_at=800,
    ),
    ModelEntry(
        value="nvidia/nemotron-3.5-lightning:free",
        label="Nemotron 3.5 Lightning (free) — NVIDIA · Reasoning · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: empty/truncated content at both 200 and 800 tokens.",
    ),
    ModelEntry(
        value="nvidia/nemotron-3.5-content-safety:free",
        label="Nemotron 3.5 Content Safety (free) — NVIDIA · Moderation · 128K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Moderation model, not a summariser.",
    ),
    ModelEntry(
        value="openrouter/free",
        label="Free Models Router — OpenRouter · Vision · 200K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Router over random free models; truncated/empty at both 200 and 800 tokens.",
    ),
    ModelEntry(
        value="stealth/glyph-cluster",
        label="Glyph Cluster (free) — Stealth · 256K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Reasoning model: timed out (>90s) at both 200 and 800 tokens in the 2026-10 re-probe.",
    ),
    ModelEntry(
        value="poolside/laguna-xs-2.1:free",
        label="Laguna XS 2.1 (free) — Poolside · Coding · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Hit the free-tier HTTP 429 limit on every recent probe.",
    ),
    ModelEntry(
        value="nvidia/nemotron-3-super-120b-a12b:free",
        label="Nemotron 3 Super (free) — NVIDIA · 120B · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Listed free, but requests returned HTTP 404/502 in the 2026-10 re-probe.",
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
