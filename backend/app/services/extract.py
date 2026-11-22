"""Content extraction and deterministic normalization."""

from __future__ import annotations

import hashlib
import html
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
# Trailing whitespace-only lines (blank lines that still carry spaces/tabs).
_WS_ONLY_LINE_RE = re.compile(r"^[ \t]+$", re.MULTILINE)


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


# Runtime defense-in-depth for stored regexes (schemas already validate new
# input, but rows created before that cap may hold more/longer patterns):
# oversized workload is skipped rather than stalling a shared check worker.
_MAX_IGNORE_REGEX_PATTERNS = 20
_MAX_IGNORE_REGEX_PATTERN_LEN = 256
_MAX_IGNORE_REGEX_TEXT_CHARS = 1_000_000


def apply_ignore_regexes(text: str, patterns: list[str], *, preserve_markdown: bool = False) -> str:
    if len(patterns) > _MAX_IGNORE_REGEX_PATTERNS:
        raise ExtractionError(
            "normalization_failed",
            f"Too many ignore regexes (max {_MAX_IGNORE_REGEX_PATTERNS})",
        )
    if len(text) > _MAX_IGNORE_REGEX_TEXT_CHARS:
        # A pathological pattern over a multi-megabyte body can pin a worker
        # CPU core for minutes. Above the cap the regex pass is skipped
        # (deterministically), trading noise-filtering for bounded latency.
        logger.warning(
            "ignore_regexes_skipped len=%d cap=%d patterns=%d",
            len(text),
            _MAX_IGNORE_REGEX_TEXT_CHARS,
            len(patterns),
        )
        return normalize_markdown_text(text) if preserve_markdown else normalize_text(text)
    for pattern in patterns:
        if not pattern:
            continue
        if len(pattern) > _MAX_IGNORE_REGEX_PATTERN_LEN:
            raise ExtractionError(
                "normalization_failed",
                f"Ignore regex longer than {_MAX_IGNORE_REGEX_PATTERN_LEN} characters",
            )
        try:
            # pi-lens-ignore: python-unsafe-regex - validated, auth-scoped
            rx = re.compile(pattern, flags=re.MULTILINE)
        except re.error as exc:
            raise ExtractionError(
                "normalization_failed", f"Invalid ignore regex: {pattern}"
            ) from exc
        text = rx.sub("", text)
    return normalize_markdown_text(text) if preserve_markdown else normalize_text(text)


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
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Clean empty link tokens like [](url) -> url
    text = re.sub(r"\[\s*\]\(([^)\s]+)\)", r"\1", text)
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line != "")
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def normalize_markdown_text(text: str) -> str:
    """Normalize a markdown document while preserving its block structure.

    :func:`normalize_text` is meant for scraped page text: it trims every
    line and drops blank lines. That is destructive for markdown, so a
    README monitor used it and the result rendered badly — paragraph breaks
    disappeared, nested lists flattened, and indented code blocks lost their
    indentation (which also produced noisy diffs).

    This variant keeps the document shape intact:
    - line endings are normalized to ``\\n`` and a BOM is dropped;
    - blank lines, indentation and trailing spaces are preserved (they are
      meaningful in markdown: paragraph breaks, nested lists, hard line
      breaks, indented code);
    - runs of 3+ blank lines collapse to a single blank line;
    - leading/trailing blank lines are trimmed.

    HTML entities are deliberately *not* unescaped here: ``&lt;div&gt;``
    inside a fenced code block must stay literal, and the markdown
    renderer decodes entities for display anyway.
    """
    if not text:
        return ""
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Normalize whitespace-only lines to truly empty lines so blank-line
    # runs collapse consistently (indentation of blank lines is meaningless).
    text = _WS_ONLY_LINE_RE.sub("", text)
    # Collapse 3+ newlines (2+ blank lines) into a single blank line.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


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

    # trafilatura emits markdown where blank lines and indentation matter.
    # normalize_text() strips both, so an unchanged page could hash differently
    # on the next run (flapping); keep the block structure instead.
    text = normalize_markdown_text(md)
    return apply_ignore_regexes(text, ignore_regexes or [], preserve_markdown=True)


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

# Do NOT include whitespace in the amount itself: a page with a compare-at
# price ("$19.99 24.99") must yield two candidates, not one fictitious number.
_AMOUNT = r"(\d[\d.,]*)"


def _normalize_amount(raw: str, *, dot_is_grouping: bool = False) -> str:
    """Canonicalize a matched amount to dot-decimal without grouping.

    Handles both ``1,234.56`` and ``1.234,56`` conventions: when both
    separators appear, the *last* one is the decimal separator. A lone comma
    followed by 1–2 digits is decimal (``19,99``); a lone separator followed
    A dot with a 3-digit tail stays decimal (``10.000``, ``0.500``); a comma
    with a 3-digit tail is a thousands group (``1,200``). Trailing-symbol
    (European) prices opt into dot-as-grouping at the candidate layer.
    """
    s = re.sub(r"\s+", "", raw).strip(".,")
    if not s or not re.search(r"\d", s):
        return ""
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot != -1 and last_comma != -1:
        # Both present → later one separates decimals, the other groups.
        dec_idx = max(last_dot, last_comma)
        dec_part = s[dec_idx + 1 :]
        int_part = re.sub(r"[.,]", "", s[:dec_idx])
        return f"{int_part}.{dec_part}"
    sep_char = "." if last_dot != -1 else ("," if last_comma != -1 else "")
    if sep_char:
        head, _, tail = s.rpartition(sep_char)
        if head and len(tail) == 3 and (
            sep_char == "," or (sep_char == "." and dot_is_grouping)
        ):
            # A 3-digit group: ``1,200`` everywhere, and ``1.200 ¥`` on the
            # trailing-symbol (European) path. Bare ``10.000``/``0.500``
            # keep their dot: losing it would 1000x the price.
            return re.sub(r"[.,]", "", s)
        if sep_char == "." and s.count(".") > 1:
            # Multiple dots are grouping (``1.234.567``).
            return re.sub(r"[.,]", "", s)
        if 1 <= len(tail) <= 3:
            # ``19.99``, ``19,99``, ``10.000``, ``0.500``.
            return f"{head.replace(',', '').replace('.', '')}.{tail}"
        return re.sub(r"[.,]", "", s)
    return s


# Labels marking the current price vs a struck-through compare-at price.
# Only text *preceding* a candidate is inspected: in "Was $99, now $49" the
# first candidate must not be tagged "now" by the second one's label.
_CURRENT_PRICE_RE = re.compile(r"\b(now|final|current|sale|today)\b", re.I)
_COMPARE_AT_RE = re.compile(r"\b(was|old|reg(?:ular)?|compare(?:-at)?|rrp|list)\b", re.I)


def _price_candidates(text: str) -> list[tuple[int, str, str]]:
    """Candidates as ``(position, value, preceding_context)`` in page order."""
    candidates: list[tuple[int, str, str]] = []

    def add(
        position: int, code: str, amount_raw: str, *, dot_grouping: bool = False
    ) -> None:
        amount = _normalize_amount(amount_raw, dot_is_grouping=dot_grouping)
        if amount:
            context = text[max(0, position - 64) : position].lower()
            candidates.append((position, f"{code} {amount}", context))

    sym_cls = re.escape(_PRICE_SYMBOLS)
    code_alt = "|".join(_PRICE_CODES)

    # 1) Symbol-led: $19.99, € 20, £15.00, ¥1,200
    for match in re.finditer(rf"([{sym_cls}])\s*{_AMOUNT}", text):
        add(match.start(), _SYMBOL_TO_CODE.get(match.group(1), "USD"), match.group(2))

    # 2) Symbol-after (common in Europe): 19,99 €, 1290 Ft-style trailing symbol
    for match in re.finditer(rf"{_AMOUNT}\s*([{sym_cls}])", text):
        # Trailing symbol = European convention: 1.200 is a grouped thousand.
        add(
            match.start(),
            _SYMBOL_TO_CODE.get(match.group(2), "USD"),
            match.group(1),
            dot_grouping=True,
        )

    # 3) ISO code before or after the number: USD 19.99 / 19.99 EUR
    for match in re.finditer(rf"\b({code_alt})\s*{_AMOUNT}", text, re.IGNORECASE):
        add(match.start(), match.group(1).upper(), match.group(2))
    for match in re.finditer(rf"{_AMOUNT}\s*\b({code_alt})\b", text, re.IGNORECASE):
        add(match.start(), match.group(2).upper(), match.group(1))

    # 4) Bare decimal labelled as price-like text. Only used as a last resort
    # when no currency symbol or ISO code was found, so that an attribute like
    # class="price" cannot shadow a real "$29.99" candidate.
    if not candidates:
        bare = re.search(r"(?:price|cost|amount)\D{0,20}?" + _AMOUNT, text, re.I)
        if bare:
            amount = _normalize_amount(bare.group(1))
            if amount:
                context = text[max(0, bare.start() - 64) : bare.start()].lower()
            candidates.append((bare.start(), amount, context))

    return sorted(candidates, key=lambda candidate: candidate[0])


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

        search_html = tree.html or html
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

    def _rank(context: str) -> int:
        # Use the label closest to the amount: "Was $99, final $49" must not
        # let the older "was" tag the second candidate as a compare-at price.
        now = max((m.end() for m in _CURRENT_PRICE_RE.finditer(context)), default=-1)
        was = max((m.end() for m in _COMPARE_AT_RE.finditer(context)), default=-1)
        if now >= 0 and now > was:
            return 0
        if was >= 0 and was > now:
            return 2
        return 1

    # An explicit current-price label wins over a compare-at ("was") price;
    # without labels the first candidate in document order still wins.
    return min(candidates, key=lambda c: (_rank(c[2]), c[0]))[1]
