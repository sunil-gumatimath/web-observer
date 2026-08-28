"""Live demo: main-content extraction vs whole-body on HN + an article page."""
import httpx

from app.services.extract import extract_main_markdown, extract_markdown

SITES = {
    "HN /news": "https://news.ycombinator.com/news",
    "Paul Graham article": "https://paulgraham.com/prepare.html",
}

with httpx.Client(follow_redirects=True, timeout=20, headers={"User-Agent": "Mozilla/5.0"}) as c:
    for name, url in SITES.items():
        html = c.get(url).text
        main = extract_main_markdown(html, base_url=url)
        full = extract_markdown(html)
        print(f"--- {name}")
        print(f"whole-body: {len(full)} chars | first 100: {full[:100]!r}")
        if main:
            print(f"main-only : {len(main)} chars | first 200: {main[:200]!r}")
        else:
            print("main-only : None (would fall back to whole-body)")
