"""RSS/Atom feed item extraction."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote

from app.services.extract import ExtractionError

ATOM_NS = "http://www.w3.org/2005/Atom"
# Namespaces are compared lowercased (see ``_split_tag``), so the Atom namespace
# needs its comparable form: matching the verbatim URL meant ``<atom:link>``
# inside an RSS ``<item>`` was never recognised as part of the feed.
_ATOM_NS_LOWER = ATOM_NS.lower()

# Link relations that identify the item itself. Anything else ("self",
# "enclosure", "replies", ...) points at the feed or an asset, so it may only be
# used when the item carries no alternate link at all.
_ENTRY_LINK_RELS = frozenset(("", "alternate"))


def _split_tag(tag: object) -> tuple[str, str]:
    """``(namespace, local_name)`` for an ElementTree tag, both lowercased."""
    if not isinstance(tag, str):
        return "", ""
    namespace, _, local_name = tag.rpartition("}")
    return namespace.lstrip("{").lower(), local_name.lower()


def _local_name(tag: object) -> str:
    return _split_tag(tag)[1]


def _belongs_to_feed(node: ET.Element, parent_ns: str, root_ns: str) -> bool:
    """True when *node* uses the feed's own vocabulary, not an extension one.

    Namespaced look-alikes strip to the same local name (``itunes:title``,
    ``media:title``, ``dc:title`` all end up as ``title``), so matching on the
    name alone let a vendor element stand in for the item's real ``<title>``.
    Unqualified, inherited and Atom elements are accepted; foreign extension
    namespaces are skipped.
    """
    namespace, _ = _split_tag(node.tag)
    return not namespace or namespace in (parent_ns, root_ns, _ATOM_NS_LOWER)


def _atom_entry_fields(entry: ET.Element, root_ns: str) -> tuple[str, str, str]:
    """Return ``(title, link, entry_id)`` for one Atom ``<entry>``.

    The first value of each field wins, so document order stays meaningful:
    the entry's own (alternate/unspecified) link beats a ``rel="self"`` one
    no matter where the producer put it.
    """
    entry_ns = _split_tag(entry.tag)[0]
    title = ""
    link = ""
    fallback_link = ""
    entry_id = ""
    for child in entry:
        if not _belongs_to_feed(child, entry_ns, root_ns):
            continue
        name = _local_name(child.tag)
        if name == "title":
            value = (child.text or "").strip()
            if value and not title:
                title = value
        elif name == "link":
            # Atom puts the target in ``href``; some producers wrap it in text.
            href = (child.attrib.get("href") or "").strip() or (child.text or "").strip()
            if not href:
                continue
            rel = (child.attrib.get("rel") or "").strip().lower()
            if rel in _ENTRY_LINK_RELS:
                if not link:
                    link = href
            elif not fallback_link:
                fallback_link = href
        elif name in ("id", "guid"):
            value = (child.text or "").strip()
            if value and not entry_id:
                entry_id = value
    return title, (link or fallback_link), entry_id


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

    root_ns, root_name = _split_tag(root.tag)
    items: list[str] = []

    def _append(label: str, href: str, identity: str) -> None:
        item = f"[{label}]({href})" if href else label
        items.append(
            f"{item}<!--mtw-id:{quote(identity, safe='')}-->"
            if identity and include_identity
            else item
        )

    # Detect Atom vs RSS by the root element itself.
    if root_name == "feed":
        # Atom: <entry><title> + <link href> + <id>
        entries = root.findall("atom:entry", {"atom": ATOM_NS})
        if not entries:
            entries = [e for e in root.iter() if _local_name(e.tag) == "entry"]
        for entry in entries:
            title, link, entry_id = _atom_entry_fields(entry, root_ns)
            label = title or entry_id or link
            if not label:
                continue
            _append(label, link or entry_id, entry_id or link)
    else:
        # RSS: <channel><item><title>/<link>/<guid> (also RSS 1.0 / RDF items)
        for node in root.iter():
            if _local_name(node.tag) != "item":
                continue
            item_ns = _split_tag(node.tag)[0]
            title = ""
            link = ""
            fallback_link = ""
            guid = ""
            for child in node:
                if not _belongs_to_feed(child, item_ns, root_ns):
                    continue
                name = _local_name(child.tag)
                if name == "title":
                    value = (child.text or "").strip()
                    if value and not title:
                        title = value
                elif name == "link":
                    # RSS carries the URL as text; Atom-style href is tolerated.
                    # Same relation policy as ``_atom_entry_fields``: a native
                    # link or an Atom alternate wins over rel="self" no matter
                    # where in the item the producer put them.
                    href = (child.text or "").strip()
                    if not href:
                        href = (child.attrib.get("href") or "").strip()
                    if not href:
                        continue
                    rel = (child.attrib.get("rel") or "").strip().lower()
                    if rel in _ENTRY_LINK_RELS:
                        if not link:
                            link = href
                    elif not fallback_link:
                        fallback_link = href
                elif name in ("guid", "id"):
                    value = (child.text or "").strip()
                    if value and not guid:
                        guid = value
            link = link or fallback_link
            label = title or guid or link
            if not label:
                continue
            _append(label, link or guid, guid or link)

    if not items:
        raise ExtractionError("extraction_failed", "RSS feed contained no items")
    return items
