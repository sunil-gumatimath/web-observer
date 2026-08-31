"""Content extraction and deterministic normalization."""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata

from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)

try:
    from markdownify import markdownify
except ImportError:  # pragma: no cover - fallback when the optional dep is missing
    markdownify = None

try:
    import trafilatura
except ImportError:  # pragma: no cover - fallback when the optional dep is missing
    trafilatura = None


class ExtractionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def extract_text(
    html: str,
    *,
    ignore_selectors: list[str] | None = None,
    ignore_regexes: list[str] | None = None,
) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()

    # User-configured ignore selectors (noise reduction)
    for selector in ignore_selectors or []:
        if not selector or not str(selector).strip():
            continue
        try:
            for node in tree.css(str(selector).strip()):
                node.decompose()
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(
                "extraction_failed", f"Invalid ignore selector: {selector}"
            ) from exc

    body = tree.body
    raw = body.text(separator="\n", strip=True) if body else tree.text(separator="\n", strip=True)

    text = normalize_text(raw)
    return apply_ignore_regexes(text, ignore_regexes or [])


def apply_ignore_regexes(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        if not pattern:
            continue
        try:
            # pi-lens-ignore: python-unsafe-regex - validated, auth-scoped
            rx = re.compile(pattern, flags=re.MULTILINE)
        except re.error as exc:
            raise ExtractionError(
                "normalization_failed", f"Invalid ignore regex: {pattern}"
            ) from exc
        text = rx.sub("", text)
    return normalize_text(text)


def extract_markdown(
    html: str,
    *,
    ignore_selectors: list[str] | None = None,
    ignore_regexes: list[str] | None = None,
) -> str:
    """Convert a page to readable Markdown for ``page_content`` monitors.

    Unlike :func:`extract_text` (which flattens the DOM to bare text), this
    preserves headings, links, lists, emphasis and images so the line-level
    diff (``unified_diff``) reads like a document diff rather than a wall of
    plain text. Same noise-reduction hooks as :func:`extract_text`.
    """
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    _strip_boilerplate(tree)

    for selector in ignore_selectors or []:
        if not selector or not str(selector).strip():
            continue
        try:
            for node in tree.css(str(selector).strip()):
                node.decompose()
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(
                "extraction_failed", f"Invalid ignore selector: {selector}"
            ) from exc

    body = tree.body
    body_html = (body.html if body else str(tree)) or ""
    if markdownify is None:
        raw = extract_text(
            body_html,
            ignore_selectors=ignore_selectors,
            ignore_regexes=ignore_regexes,
        )
        return raw
    md_text = markdownify(
        body_html,
        heading_style="ATX",
        bullets="-",
        convert=[
            "a",
            "img",
            "strong",
            "em",
            "code",
            "pre",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "blockquote",
            "table",
        ],
        # Without this, markdownify silently drops any <img> whose direct
        # parent is an inline element (<a><img></a>, <span>, <p> wrappers...)
        # and keeps only its alt text — losing most linked logos/thumbnails.
        keep_inline_images_in=[
            "a",
            "p",
            "div",
            "td",
            "th",
            "li",
            "span",
            "figure",
        ],
    )
    text = normalize_text(md_text)
    return apply_ignore_regexes(text, ignore_regexes or [])


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line != "")
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


# Minimum readable size for a main-content extraction to be trusted. Below this
# the detector most likely missed the real content (or the page is a shell), so
# we fall back to whole-body markdown.
_MIN_MAIN_CONTENT_CHARS = 200


def _strip_boilerplate(tree: HTMLParser) -> None:
    """Remove common chrome that trafilatura/markdownify miss on React-heavy pages."""
    for sel in (
        "nav",
        "header",
        "footer",
        "aside",
        '[role="navigation"]',
        '[role="banner"]',
        '[role="contentinfo"]',
        ".nav",
        ".navbar",
        ".header",
        ".footer",
        ".cookie",
        ".cookies",
    ):
        try:
            for node in tree.css(sel):
                node.decompose()
        except Exception:
            pass


def extract_main_markdown(
    html: str,
    *,
    base_url: str | None = None,
    ignore_selectors: list[str] | None = None,
    ignore_regexes: list[str] | None = None,
) -> str | None:
    """Extract the *main content* of a page as markdown (webdog parity).

    Uses trafilatura's readability engine — the self-hosted equivalent of
    Context.dev's ``useMainContentOnly`` scrape — so navigation bars, headers,
    footers, cookie banners and ads are stripped before conversion. Returns
    ``None`` when no main content could be detected or the result is too small;
    callers should fall back to :func:`extract_markdown` (whole body).
    """
    if trafilatura is None:
        return None

    # Pre-clean with the same noise hooks as extract_text/extract_markdown so
    # user-configured ignore selectors still apply before detection.
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    _strip_boilerplate(tree)
    for selector in ignore_selectors or []:
        if not selector or not str(selector).strip():
            continue
        try:
            for node in tree.css(str(selector).strip()):
                node.decompose()
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(
                "extraction_failed", f"Invalid ignore selector: {selector}"
            ) from exc
    cleaned = tree.html or html

    try:
        md = trafilatura.extract(
            cleaned,
            url=base_url or None,
            output_format="markdown",
            include_images=True,
            include_links=True,
            include_tables=True,
            include_formatting=True,
            favor_recall=True,
        )
    except Exception:  # noqa: BLE001 - extraction must never crash a check
        logger.exception("trafilatura main-content extraction failed; falling back")
        return None

    if not md or len(md.strip()) < _MIN_MAIN_CONTENT_CHARS:
        return None

    text = normalize_text(md)
    return apply_ignore_regexes(text, ignore_regexes or [])


def content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Price extraction (product_price mode)
# ---------------------------------------------------------------------------

# Currency symbols we recognise when auto-detecting a price.
_PRICE_SYMBOLS = "$€£¥₹"
_SYMBOL_TO_CODE = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
}
# ISO codes recognised before/after an amount.
_PRICE_CODES = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "INR",
    "CAD",
    "AUD",
    "CHF",
    "CNY",
    "BRL",
    "SEK",
    "NOK",
    "DKK",
    "PLN",
    "CZK",
    "HUF",
    "MXN",
    "ZAR",
    "SGD",
    "HKD",
    "NZD",
    "TRY",
    "AED",
    "SAR",
    "ILS",
    "KRW",
    "THB",
)

_AMOUNT = r"(\d[\d.,\s]*)"


def _normalize_amount(raw: str) -> str:
    """Canonicalize a matched amount to dot-decimal without grouping.

    Handles both ``1,234.56`` and ``1.234,56`` conventions: when both
    separators appear, the *last* one is the decimal separator. A lone comma
    followed by 1–2 digits is decimal (``19,99``); a lone separator followed
    by exactly 3 digits is grouping (``10.000``, ``1,200``).
    """
    s = re.sub(r"\s+", "", raw).strip(".,")
    if not s or not re.search(r"\d", s):
        return ""
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    dec_idx = max(last_dot, last_comma)
    if last_dot != -1 and last_comma != -1:
        # Both present → later one separates decimals, the other groups.
        dec_part = s[dec_idx + 1 :]
        int_part = re.sub(r"[.,]", "", s[:dec_idx])
        return f"{int_part}.{dec_part}"
    sep_char = "." if last_dot != -1 else ("," if last_comma != -1 else "")
    if sep_char:
        head, _, tail = s.rpartition(sep_char)
        tail_digits = len(tail)
        if len(tail) == 3 and head:
            # ``10.000`` / ``1,200`` → grouping, not decimals.
            return re.sub(r"[.,]", "", s)
        if 1 <= tail_digits <= 2:
            # Decimal separator (``19.99`` / ``19,99``).
            return f"{head.replace(',', '').replace('.', '')}.{tail}"
        # No/far decimals → treat all separators as grouping.
        return re.sub(r"[.,]", "", s)
    return s


def _price_candidates(text: str) -> list[str]:
    candidates: list[str] = []

    def add(code: str, amount_raw: str) -> None:
        amount = _normalize_amount(amount_raw)
        if amount:
            candidates.append(f"{code} {amount}")

    sym_cls = re.escape(_PRICE_SYMBOLS)
    code_alt = "|".join(_PRICE_CODES)

    # 1) Symbol-led: $19.99, € 20, £15.00, ¥1,200
    for sym, num in re.findall(rf"([{sym_cls}])\s*{_AMOUNT}", text):
        add(_SYMBOL_TO_CODE.get(sym, "USD"), num)

    # 2) Symbol-after (common in Europe): 19,99 €, 1290 Ft-style trailing symbol
    for num, sym in re.findall(rf"{_AMOUNT}\s*([{sym_cls}])", text):
        add(_SYMBOL_TO_CODE.get(sym, "USD"), num)

    # 3) ISO code before or after the number: USD 19.99 / 19.99 EUR
    for code, num in re.findall(rf"\b({code_alt})\s*{_AMOUNT}", text, re.IGNORECASE):
        add(code.upper(), num)
    for num, code in re.findall(rf"{_AMOUNT}\s*\b({code_alt})\b", text, re.IGNORECASE):
        add(code.upper(), num)

    # 4) Bare decimal labelled as price-like text.
    bare = re.search(r"(?:price|cost|amount)\D{0,20}?" + _AMOUNT, text, re.I)
    if bare:
        amount = _normalize_amount(bare.group(1))
        if amount:
            candidates.append(amount)

    return candidates


def extract_price(
    html: str,
    *,
    css_selector: str | None = None,
    ignore_selectors: list[str] | None = None,
) -> str:
    """Best-effort price detection for ``product_price`` monitors.

    Searches the page for a currency symbol or ISO code next to an amount and
    returns a stable string such as ``"USD 19.99"``. Raises
    :class:`ExtractionError` (code ``price_not_found``) when nothing matches.

    Hardening over the raw-regex version:

    * ``<script>``/``<style>``/``<noscript>``/``<template>`` and user
      ``ignore_selectors`` are decomposed first, so JSON-LD / dataLayer price
      blobs can no longer shadow the rendered price.
    * When ``css_selector`` is provided the search is scoped to those nodes
      (optional targeting, same field as other modes).
    * Amounts normalize across conventions: ``$19.99``, ``19,99 €``,
      ``€ 1.299,00``, ``USD 19.99`` and ``1200 JPY`` all work; grouping
      separators are stripped so hashes stay stable.
    """
    try:
        tree = HTMLParser(html)
        for node in tree.css("script, style, noscript, template"):
            node.decompose()
        for selector in ignore_selectors or []:
            if selector and str(selector).strip():
                try:
                    for node in tree.css(str(selector).strip()):
                        node.decompose()
                except Exception as sel_exc:  # noqa: BLE001 - invalid selector
                    logger.debug(
                        "price_ignore_selector_skipped selector=%s error=%s",
                        selector,
                        sel_exc,
                    )

        search_html = html
        if css_selector and str(css_selector).strip():
            nodes = tree.css(str(css_selector).strip())
            if nodes:
                search_html = " ".join(n.html or "" for n in nodes)

        text = search_html
        body = tree.body
        if not css_selector and body is not None:
            # Prefer visible text; fall back to remaining HTML for meta tags.
            visible = body.text(separator=" ", strip=True)
            text = f"{visible} {search_html}"
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - malformed HTML etc.
        raise ExtractionError("extraction_failed", f"Price scan failed: {exc}") from exc

    candidates = _price_candidates(text)
    if not candidates:
        raise ExtractionError("price_not_found", "No price found on the page")
    return candidates[0]
