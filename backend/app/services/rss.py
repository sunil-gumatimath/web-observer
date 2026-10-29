"""RSS/Atom feed item extraction."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote

from app.services.extract import ExtractionError


def extract_rss_items(text: str, *, include_identity: bool = False) -> list[str]:
    """Parse RSS/Atom XML into display items, optionally including diff identities."""
    text = (text or "").strip()
    if not text:
        raise ExtractionError("extraction_failed", "Empty RSS feed")
    # Strip BOM
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError as exc:
        raise ExtractionError("extraction_failed", f"Invalid RSS/Atom XML: {exc}") from exc

    tag = root.tag.lower()
    items: list[str] = []

    # Detect Atom vs RSS
    if "feed" in tag:
        # Atom: <entry><title> + <link href> + <id>
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            entries = [e for e in root.iter() if e.tag.lower().endswith("entry")]
        for entry in entries:
            title = ""
            link = ""
            gid = ""
            for child in entry:
                t = child.tag.lower()
                if t.endswith("title") and child.text:
                    title = child.text.strip()
                elif t.endswith("link"):
                    href = child.attrib.get("href", "").strip()
                    if href:
                        link = href
                    elif child.text:
                        link = child.text.strip()
                elif t.endswith("id") and child.text:
                    gid = child.text.strip()
            label = title or gid or link
            if not label:
                continue
            href = link or gid
            identity = gid or link
            item = f"[{label}]({href})" if href else label
            items.append(
                f"{item}<!--mtw-id:{quote(identity, safe='')}-->"
                if identity and include_identity
                else item
            )
    else:
        # RSS: <channel><item><title>/<link>/<guid>
        for item in root.iter():
            if item.tag.lower().endswith("item"):
                title = ""
                link = ""
                guid = ""
                for child in item:
                    t = child.tag.lower()
                    if t.endswith("title") and child.text:
                        title = child.text.strip()
                    elif t.endswith("link") and child.text:
                        link = child.text.strip()
                    elif t.endswith("guid") and child.text:
                        guid = child.text.strip()
                label = title or guid or link
                if not label:
                    continue
                href = link or guid
                identity = guid or link
                item_text = f"[{label}]({href})" if href else label
                items.append(
                    f"{item_text}<!--mtw-id:{quote(identity, safe='')}-->"
                    if identity and include_identity
                    else item_text
                )

    if not items:
        raise ExtractionError("extraction_failed", "RSS feed contained no items")
    return items
