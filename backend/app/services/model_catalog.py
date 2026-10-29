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
    recommended: bool = False
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
# The live gateway catalog was checked on 2026-10-29. This is a curated
# shortlist of five free text-chat models for this app, based on app-prompt
# probes rather than Kilo's coding rankings. Laguna is the tested default.
#
# ``verified_at`` comes from those probes. 200 = fits the app's default cap;
# 800 = passes once its own cap is applied; None = no complete reply observed
# (reasoning burned the budget, the model returned non-JSON, timed out, was
# rate-limited, or was not served).
# ---------------------------------------------------------------------------
_KILO_MODELS: list[ModelEntry] = [
    ModelEntry(
        value="poolside/laguna-s-2.1:free",
        label="Laguna S 2.1 (free) — Poolside · 262K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Recommended default. Passed summary + watch/semantic triage, change Q&A, and digest probes on 2026-10-29. Previously completed strict JSON at the default 200-token cap in 2/2 probes.",
        recommended=True,
        verified_at=200,
    ),
    ModelEntry(
        value="nvidia/nemotron-3.5-super-vl:free",
        label="Nemotron 3.5 Super VL (free) — NVIDIA · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Passed all three app feature probes on 2026-10-29. Kilo highlights it in its free catalog; NVIDIA free endpoints are trial use, so avoid personal or confidential content.",
        verified_at=800,
    ),
    ModelEntry(
        value="nvidia/nemotron-3-ultra-550b-a55b:free",
        label="Nemotron 3 Ultra (free) — NVIDIA · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Passed all three app feature probes on 2026-10-29, but was slower than the recommended default. NVIDIA free endpoints are trial use; avoid personal or confidential content.",
        verified_at=800,
    ),
    ModelEntry(
        value="reflection/beam-free",
        label="Beam 1.0 (free) — Reflection · 1M ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Passed all three app feature probes on 2026-10-29. Its summary needs the larger 800-token output cap.",
        verified_at=800,
    ),
    ModelEntry(
        value="dots-studio/dots-3-note-preview:free",
        label="Dots3-Note Preview (free) — Dots Studio · 512K ctx",
        provider="kilo",
        base=KILO_BASE,
        note="Completed summary + triage once at 800 tokens, but Q&A and digest returned HTTP 403 with the current Kilo key on 2026-10-29. Availability is not consistent across features.",
        verified_at=800,
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
