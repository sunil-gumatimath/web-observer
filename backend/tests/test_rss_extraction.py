"""rss_feed extraction: element names, namespaces and link relations.

Element matching used to be a substring test on the tag (``.endswith("title")``)
with last-value-wins, so a ``<subtitle>`` or an ``<itunes:title>`` replaced the
item's real title and a ``rel="self"`` link replaced the entry's own URL. These
tests pin the exact-name, namespace-aware behaviour.
"""

from __future__ import annotations

from app.services.rss import extract_rss_items

ATOM_WITH_SUBTITLE_AND_SELF_LINK = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example feed</title>
  <entry>
    <title>Real entry title</title>
    <subtitle>Feed-level blurb that must not win</subtitle>
    <link rel="alternate" href="https://example.com/post-1"/>
    <link rel="self" href="https://example.com/feed.xml"/>
    <id>tag:example.com,2026:1</id>
  </entry>
</feed>
"""

RSS_WITH_ITUNES_TITLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Podcast</title>
    <item>
      <title>Episode 12: the real one</title>
      <itunes:title>Episode 12</itunes:title>
      <link>https://example.com/ep12</link>
      <guid>https://example.com/ep12</guid>
    </item>
  </channel>
</rss>
"""

ATOM_SELF_LINK_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Only a self link</title>
    <link rel="self" href="https://example.com/only-self"/>
  </entry>
</feed>
"""

RSS_1_0_RDF = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/">
  <channel><title>RDF feed</title></channel>
  <item>
    <title>RDF item</title>
    <link>https://example.com/rdf-1</link>
  </item>
</rdf:RDF>
"""


def test_atom_subtitle_does_not_replace_the_entry_title() -> None:
    items = extract_rss_items(ATOM_WITH_SUBTITLE_AND_SELF_LINK)
    assert items == ["[Real entry title](https://example.com/post-1)"]


def test_atom_self_link_does_not_replace_the_entry_link() -> None:
    items = extract_rss_items(ATOM_WITH_SUBTITLE_AND_SELF_LINK)
    assert "feed.xml" not in items[0]


def test_atom_entry_identity_comes_from_the_id() -> None:
    identity = "<!--mtw-id:tag%3Aexample.com%2C2026%3A1-->"
    items = extract_rss_items(ATOM_WITH_SUBTITLE_AND_SELF_LINK, include_identity=True)
    assert items == [f"[Real entry title](https://example.com/post-1){identity}"]


def test_atom_self_link_is_kept_as_a_fallback() -> None:
    items = extract_rss_items(ATOM_SELF_LINK_ONLY)
    assert items == ["[Only a self link](https://example.com/only-self)"]


def test_rss_itunes_title_does_not_replace_the_item_title() -> None:
    items = extract_rss_items(RSS_WITH_ITUNES_TITLE)
    assert items == ["[Episode 12: the real one](https://example.com/ep12)"]


def test_rss_extension_title_before_the_real_title_is_ignored() -> None:
    feed = (
        "<rss version='2.0' xmlns:itunes='http://www.itunes.com/dtds/podcast-1.0.dtd'>"
        "<channel><item>"
        "<itunes:title>Episode 12</itunes:title>"
        "<title>Episode 12: the real one</title>"
        "<link>https://example.com/ep12</link>"
        "</item></channel></rss>"
    )
    assert extract_rss_items(feed) == ["[Episode 12: the real one](https://example.com/ep12)"]


def test_rss_1_0_namespaced_items_are_extracted() -> None:
    items = extract_rss_items(RSS_1_0_RDF)
    assert items == ["[RDF item](https://example.com/rdf-1)"]


def test_plain_rss_and_atom_still_extract() -> None:
    rss = (
        "<rss version='2.0'><channel>"
        "<item><title>One</title><link>https://example.com/1</link></item>"
        "<item><title>Two</title><link>https://example.com/2</link></item>"
        "</channel></rss>"
    )
    assert extract_rss_items(rss) == [
        "[One](https://example.com/1)",
        "[Two](https://example.com/2)",
    ]
    atom = (
        "<feed xmlns='http://www.w3.org/2005/Atom'>"
        "<entry><title>Atom one</title><link href='https://example.com/a1'/>"
        "<id>tag:example.com,2026:1</id></entry>"
        "</feed>"
    )
    assert extract_rss_items(atom) == ["[Atom one](https://example.com/a1)"]
