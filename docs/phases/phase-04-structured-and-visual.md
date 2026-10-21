<p align="center">
  <img src="../../assets/web-observer.svg" alt="Web Observer logo" width="320" />
</p>

# Phase 4 — Structured & Visual Monitoring

## Modes

Actual shipped modes (`backend/app/schemas.py:225-227`, `backend/app/models/entities.py:31`):

| Mode | What it watches | Extract | Worker |
| ------ | -------- | --------- | -------- |
| `page_content` | A single page, scraped to markdown | Normalized markdown text (`extract_markdown`) – line-level unified diff | HTTP (or browser if `js_required`) |
| `site_links` | The site's sitemap | Sitemap URLs joined by newline (`sitemap_monitor_text`) – added/removed link diff | HTTP |
| `product_price` | A product page | Price/currency string (`extract_price`, e.g. `USD 19.99`) – checks every 24h by default (`1440m`) | HTTP / browser |
| `list_items` | A CSS-selector link list on a page | HTML list items as `[text](url)` (`extract_html_list`) – added/removed link diff | HTTP / browser |
| `json_field` | A single value in a JSON API response | Scalar extracted via a JSONPath-style query (e.g. `$.data.price`) – hash diff of the normalized value | HTTP / browser |
| `rss_feed` | An RSS/Atom feed | Feed entries joined by newline – added/removed entry diff | HTTP (`js_required` rejected) |
| `readme` | A GitHub repository README (`owner/repo` or full URL, `/tree | blob/<branch>`,`.git` all accepted) | Normalized markdown – line-level unified diff; fetched via GitHub API first, then capped raw probes | HTTP (`js_required` rejected) |
| `visual` | A page's rendered appearance | Full-page screenshot perceptual hash (DCT pHash, hamming distance vs `VISUAL_PHASH_THRESHOLD`; legacy aHash vs `VISUAL_AHASH_THRESHOLD` for snapshots captured before pHash) – change when distance exceeds threshold | Browser |
| `security_scan` | A URL's security posture on Cloudflare's edge | URL Scanner verdict flattened to one fact per line (`malicious=`, `categories=`, `tags=`, `certificate=`, `server=`, `asn=`, `tech=`) – added/removed fact diff | Cloudflare edge (`js_required` rejected) |

`css_selector` is required for `list_items` (`backend/app/schemas.py:256-264`). For `json_field`, the URL must return JSON and the JSONPath-style query is stored in the `css_selector` field. `site_links` ignores `css_selector` and `js_required`. `js_required` is rejected for `site_links`, `rss_feed`, `readme`, and `security_scan` (plain-HTTP fetch, or rendering on Cloudflare's edge); other modes may use the browser queue.

## Structured diffs

- **JSON field:** hash of normalized scalar or sorted JSON  
- **List:** multiline `- item` baseline; change event shows `+` / `-` lines  

## Visual

Screenshots are available two ways:

1. **Opt-in per monitor** with `screenshots_enabled` (`monitors.screenshots_enabled`, default off) — works for every mode (see capture rules below).
2. **First-class `visual` mode** (`MonitorMode.VISUAL`) — the check compares perceptual distance (DCT pHash against `VISUAL_PHASH_THRESHOLD`, aHash against `VISUAL_AHASH_THRESHOLD` for pre-pHash snapshots) instead of text hashing; routed to the browser queue like `js_required` monitors.

Capture rules (both paths):

- When enabled, each check best-effort captures a full-page Playwright screenshot via
  `visual.py` + subprocess `playwright_job` (Windows-safe) and attaches it to the run/alert
  (`backend/app/services/pipeline.py`). A missing browser or failed capture never fails the check.
- Each PNG is stored in object storage; a DCT perceptual hash (pHash, 256-bit, via Pillow) is
  computed for similarity comparison against `VISUAL_PHASH_THRESHOLD` (default hamming
  distance 8 of 256 bits). Snapshots captured before the pHash path existed keep the legacy
  64-bit aHash and `VISUAL_AHASH_THRESHOLD` (default 5).
- Works for every mode; `js_required` monitors additionally use the same Playwright stack for
  page rendering.
Current behavior (post-roadmap): captures happen only on non-noise signal changes; needs 2 signal changes for before/after comparison.

## Config

```env
VISUAL_PHASH_THRESHOLD=8
VISUAL_AHASH_THRESHOLD=5
MAX_BROWSER_CHECKS_PER_DAY=50
```
