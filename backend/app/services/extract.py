"""Content extraction and deterministic normalization."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from selectolax.parser import HTMLParser


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
            raise ExtractionError("extraction_failed", f"Invalid ignore selector: {selector}") from exc

    body = tree.body
    raw = body.text(separator="\n", strip=True) if body else tree.text(separator="\n", strip=True)

    text = normalize_text(raw)
    return apply_ignore_regexes(text, ignore_regexes or [])


def apply_ignore_regexes(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        if not pattern:
            continue
        try:
            text = re.sub(pattern, "", text, flags=re.MULTILINE)
        except re.error as exc:
            raise ExtractionError("normalization_failed", f"Invalid ignore regex: {pattern}") from exc
    return normalize_text(text)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line != "")
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


# Currency symbols and ISO codes we recognise when auto-detecting a price.
_PRICE_SYMBOLS = "$€£¥₹"
_PRICE_CODES = ("USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD", "CHF", "CNY", "BRL")


def extract_price(html: str) -> str:
    """Best-effort price detection for ``product_price`` monitors.

    Searches the raw HTML (and falls back to normalised text) for a currency
    symbol or ISO code followed by an amount, returning a stable string such
    as ``"USD 19.99"``. Raises :class:`ExtractionError` if no price is found.
    """
    candidates: list[str] = []

    # Symbol-led: $19.99, € 20, £15.00, ¥1,200
    sym_re = re.compile(
        r"([" + re.escape(_PRICE_SYMBOLS) + r"])\s*(\d[\d,]*\.?\d{0,2})"
    )
    for sym, num in sym_re.findall(html):
        candidates.append(f"{sym}{num}")

    # Code-led: 19.99 USD, 1,200 EUR
    code_re = re.compile(
        r"(\d[\d,]*\.?\d{0,2})\s*(?:" + "|".join(_PRICE_CODES) + r")\b"
    )
    for num, _ in code_re.findall(html + " "):
        candidates.append(f"{num}")

    if not candidates:
        # Fall back to a bare decimal number labelled as price-like text.
        bare = re.search(r"(?:price|cost|amount)\D*?(\d[\d,]*\.?\d{0,2})", html, re.I)
        if bare:
            candidates.append(bare.group(1))

    if not candidates:
        raise ExtractionError("extraction_failed", "No price found on the page")

    # Normalise the first match: strip grouping commas, attach a code when a
    # symbol was used (best-effort mapping) so comparisons are stable.
    first = candidates[0]
    sym_to_code = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
        "₹": "INR",
    }
    if first[0] in sym_to_code:
        amount = first[1:].replace(",", "")
        return f"{sym_to_code[first[0]]} {amount}"
    return first.replace(",", "")
