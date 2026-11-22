"""SubQ Decisions API client for fast System 1 triage, categorization, and scoring.

SubQ operates as a decision model: instead of generating freeform text, it
evaluates a diff state against typed questions (noul, choice, score) returning
calibrated probabilities and categorical selections at low latency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.security.ssrf import (
    PinnedIPTransport,
    resolve_and_validate,
)

logger = logging.getLogger(__name__)

# Valid SubQ category options aligned with Web Observer's CATEGORIES
SUBQ_CATEGORIES = {
    "pricing": "Prices, discounts, subscription tiers, plans, or billing changes",
    "availability": "Stock status, out of stock, in stock, or service availability",
    "legal": "Terms of service, privacy policy, legal disclaimers, or GDPR",
    "security": "Security disclosures, CVEs, authentication, or vulnerabilities",
    "content": "Articles, blog posts, documentation, announcements, or general text",
    "api": "API endpoints, schemas, JSON structures, or deprecations",
    "design": "Visual layout, styling, CSS, or navigation aesthetics",
    "other": "Other unclassified changes",
}

SUBQ_IMPACT_LEVELS = {
    "low": "Minor typographical, stylistic, or routine informational adjustment",
    "medium": "Noticeable content update, new non-critical feature, or minor price tweak",
    "high": "Major change such as substantial price change, breaking update, or major feature",
    "critical": "Severe outage, major security vulnerability, or urgent breaking alert",
}


@dataclass(frozen=True)
class SubQDecision:
    is_noise: bool
    noise_probability: float
    noise_reason: str | None
    category: str
    impact: str | None
    confidence: float
    tokens_used: int = 0
    model: str | None = None
    answers: dict | None = None


def _pinned_post(url: str, *, headers: dict, payload: dict, timeout: float) -> httpx.Response:
    """POST to a validated, pinned public IP without following redirects (SSRF safe)."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("Provider URL must include a hostname")
    resolved_ips = resolve_and_validate(url)
    last_exc: Exception | None = None
    for ip in resolved_ips:
        try:
            transport = PinnedIPTransport(pinned_ip=ip, server_hostname=hostname)
            with httpx.Client(
                transport=transport,
                timeout=timeout,
                follow_redirects=False,
            ) as client:
                return client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Provider resolved no usable public addresses")


def build_systemone_payload(
    *,
    monitor_name: str,
    url: str,
    mode: str,
    deterministic_summary: str,
    diff_text: str,
    watch_note: str | None = None,
    semantic_trigger: str | None = None,
    model: str = "subq-snap-preview",
) -> dict:
    """Build the request dictionary for SubQ POST /v1/systemone."""
    from app.services.ai_summary import escape_untrusted_text

    state_parts = [
        f"MONITOR: {escape_untrusted_text(monitor_name)} ({escape_untrusted_text(url)})",
        f"MODE: {mode}",
        f"DETERMINISTIC SUMMARY: {escape_untrusted_text(deterministic_summary or 'Content changed')}",
    ]
    has_watch = bool((watch_note or "").strip())
    has_semantic = bool((semantic_trigger or "").strip())
    if has_watch:
        state_parts.append(f"WATCH NOTE: {escape_untrusted_text(watch_note.strip())}")
    if has_semantic:
        state_parts.append(f"SEMANTIC TRIGGER: {escape_untrusted_text(semantic_trigger.strip())}")

    # Diff capped to avoid unnecessary token usage while preserving context
    capped_diff = (diff_text or "")[:4000]
    state_parts.append(f"DIFF:\n{escape_untrusted_text(capped_diff)}")
    state = "\n\n".join(state_parts)

    questions: dict[str, dict] = {
        "is_noise": {
            "type": "noul",
            "instructions": "Is this diff trivial noise, routine layout/timestamp shift, or tracking boilerplate?",
            "criteria": {
                "true": "Cookie banners, timestamp updates, rotating ads, dynamic session tokens, tracking pixels, or irrelevant boilerplate",
                "false": "Meaningful changes to page text, pricing, inventory availability, legal policies, documentation, security, or core content",
            },
        },
        "category": {
            "type": "choice",
            "instructions": "Which category best describes the change?",
            "criteria": SUBQ_CATEGORIES,
        },
        "impact": {
            "type": "choice",
            "instructions": "Assess the severity and business impact of this change.",
            "criteria": SUBQ_IMPACT_LEVELS,
        },
    }

    def _match_question(criteria_text: str) -> dict:
        return {
            "type": "noul",
            "instructions": (
                "Does this change match what the user is specifically watching for: "
                f"'{escape_untrusted_text(criteria_text.strip())}'?"
            ),
            "criteria": {
                "true": "The change directly aligns with or satisfies the user's specific watch note or trigger criteria",
                "false": "The change does not match or is irrelevant to the user's criteria",
            },
        }

    if has_watch and has_semantic:
        # Both criteria are active: ask about each separately so a matching
        # watch note cannot be silently ignored in favour of the trigger.
        questions["matches_watch"] = _match_question(watch_note or "")
        questions["matches_semantic"] = _match_question(semantic_trigger or "")
    elif has_watch or has_semantic:
        questions["matches_criteria"] = _match_question(
            (semantic_trigger if has_semantic else watch_note) or ""
        )

    return {
        "model": model,
        "state": state,
        "questions": questions,
    }


def _probability(value: object) -> float | None:
    """Coerce a noul answer to [0, 1]; invalid/missing values mean 'unknown'."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 1:
        return None
    return number


def parse_subq_response(
    data: dict,
    *,
    noise_threshold: float = 0.70,
    has_watch_or_semantic: bool = False,
    model_name: str | None = None,
    criteria_count: int = 1,
) -> SubQDecision:
    """Parse the SubQ /v1/systemone response into a typed SubQDecision."""
    answers = data.get("answers") or {}
    model_used = data.get("model") or model_name

    # 1. is_noise evaluation (noul: 0.0 - 1.0 probability)
    is_noise_answer = answers.get("is_noise") or {}
    noise_prob = 0.0
    if isinstance(is_noise_answer, dict):
        noise_prob = _probability(is_noise_answer.get("noul")) or 0.0

    # 2. Category selection (choice)
    cat_answer = answers.get("category") or {}
    chosen_cat = "other"
    if isinstance(cat_answer, dict):
        chosen_cat = str(cat_answer.get("choice") or "other").lower().strip()
    if chosen_cat not in SUBQ_CATEGORIES:
        chosen_cat = "other"

    # 3. Impact selection (choice: low / medium / high / critical)
    impact_answer = answers.get("impact") or {}
    chosen_impact = "low"
    if isinstance(impact_answer, dict):
        chosen_impact = str(impact_answer.get("choice") or "low").lower().strip()
    if chosen_impact not in SUBQ_IMPACT_LEVELS:
        chosen_impact = "low"

    # 4. Watch criteria / semantic trigger matching (noul: 0.0 - 1.0).
    # Invalid or missing answers are unknown, never a failed match: a broken
    # response must not silently suppress a real change.
    match_probs: list[float] = []
    for key in ("matches_criteria", "matches_watch", "matches_semantic"):
        answer = answers.get(key)
        if isinstance(answer, dict) and "noul" in answer:
            prob = _probability(answer.get("noul"))
            if prob is not None:
                match_probs.append(prob)

    # Decision logic
    is_noise = False
    noise_reason: str | None = None

    if has_watch_or_semantic and len(match_probs) >= criteria_count:
        if all(p < 0.35 for p in match_probs):
            is_noise = True
            noise_reason = f"SubQ triage: change does not match watch criteria (match probability {min(match_probs):.2f})"
        elif noise_prob >= noise_threshold:
            is_noise = True
            noise_reason = (
                f"SubQ triage: routine noise/boilerplate (noise probability {noise_prob:.2f})"
            )
    elif noise_prob >= noise_threshold:
        is_noise = True
        noise_reason = (
            f"SubQ triage: routine noise/boilerplate (noise probability {noise_prob:.2f})"
        )

    confidence = round(1.0 - noise_prob, 3) if not is_noise else round(noise_prob, 3)
    usage = data.get("usage") or {}
    tokens_used = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)

    return SubQDecision(
        is_noise=is_noise,
        noise_probability=noise_prob,
        noise_reason=noise_reason,
        category=chosen_cat,
        impact=chosen_impact,
        confidence=confidence,
        tokens_used=tokens_used,
        model=model_used,
        answers=answers,
    )


def evaluate_subq_decision(
    *,
    monitor_name: str,
    url: str,
    mode: str,
    deterministic_summary: str,
    diff_text: str,
    watch_note: str | None = None,
    semantic_trigger: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    noise_threshold: float = 0.70,
    timeout: float = 10.0,
) -> SubQDecision | None:
    """Evaluate a diff with SubQ Decisions API. Fails open (returns None) on error."""
    settings = get_settings()
    key = api_key or settings.subq_api_key
    if not key or not key.strip():
        return None

    base = (api_base or settings.subq_api_base or "https://api.subq.ai/v1").rstrip("/")
    if api_base and api_base.rstrip("/") != (settings.subq_api_base or "").rstrip("/"):
        # A custom provider base carries the same bearer token as the default
        # one, so apply the same HTTPS/SSRF guard as the LLM provider base.
        from app.services.ai_summary import validate_provider_base

        try:
            base = validate_provider_base(base, resolve_dns=False)
        except ValueError as exc:
            logger.warning("subq_invalid_provider_base error=%s", exc)
            return None
    model_name = model or settings.subq_model or "subq-snap-preview"
    endpoint = f"{base}/systemone"

    has_watch = bool((watch_note or "").strip())
    has_semantic = bool((semantic_trigger or "").strip())
    has_watch_or_semantic = has_watch or has_semantic
    payload = build_systemone_payload(
        monitor_name=monitor_name,
        url=url,
        mode=mode,
        deterministic_summary=deterministic_summary,
        diff_text=diff_text,
        watch_note=watch_note,
        semantic_trigger=semantic_trigger,
        model=model_name,
    )

    headers = {
        "Authorization": f"Bearer {key.strip()}",
        "Content-Type": "application/json",
        "User-Agent": "WebObserver/1.0",
    }

    try:
        resp = _pinned_post(endpoint, headers=headers, payload=payload, timeout=timeout)
        if resp.status_code == 200:
            return parse_subq_response(
                resp.json(),
                noise_threshold=noise_threshold,
                has_watch_or_semantic=has_watch_or_semantic,
                model_name=model_name,
                criteria_count=2 if has_watch and has_semantic else 1,
            )
        # Never echo a provider response body: it can contain echoed request
        # state (watch notes, diff excerpts) or credential fragments.
        logger.warning(
            "subq_request_failed status=%s body_bytes=%s",
            resp.status_code,
            len(resp.content or b""),
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("subq_evaluation_error error=%s", exc)
        return None
