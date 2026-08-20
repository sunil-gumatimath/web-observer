# Phase 4 — Structured & Visual Monitoring

## Modes

Actual shipped modes (`backend/app/schemas.py:10`, `backend/app/models/entities.py:30-34`):

| Mode | What it watches | Extract | Worker |
|------|--------|---------|--------|
| `page_content` | A single page, scraped to markdown | Normalized markdown text (`extract_markdown`) – line-level unified diff | HTTP (or browser if `js_required`) |
| `site_links` | The site's sitemap | Sitemap URLs joined by newline (`sitemap_monitor_text`) – added/removed link diff | HTTP |
| `product_price` | A product page | Price/currency string (`extract_price`, e.g. `USD 19.99`) – checks every 24h by default (`1440m`) | HTTP / browser |
| `list_items` | A CSS-selector link list on a page | HTML list items as `[text](url)` (`extract_html_list`) – added/removed link diff | HTTP / browser |

`css_selector` is required for `list_items` (`backend/app/schemas.py:119-121`). `site_links` ignores `css_selector` and `js_required`.

## Structured diffs

- **JSON field:** hash of normalized scalar or sorted JSON  
- **List:** multiline `- item` baseline; change event shows `+` / `-` lines  

## Visual

- Playwright screenshot (full page or region) via `visual.py` + subprocess `playwright_job` (Windows-safe)  
- Average hash (aHash) via Pillow  
- Alert only if hamming distance **>** `VISUAL_AHASH_THRESHOLD` (default 5)  
- PNG stored in object storage; metadata in `normalized_text`  

### Screenshot gallery (UI)

Visual monitors expose a **screenshot history** on the monitor detail page and a
**side-by-side visual comparison** on each visual change event.

- `GET /api/v1/workspaces/{id}/monitors/{id}/screenshots` — most-recent-first list of
  image snapshots, each with its capture timestamp, run status, aHash, and the
  perceptual-hash **distance from the previous capture** (`distance_from_previous`).
  Non-image (text/HTML) snapshots are excluded.
- `GET /api/v1/workspaces/{id}/snapshots/{id}/image` — streams the raw PNG bytes for a
  snapshot (reuses the existing local/S3 storage layer). Missing or expired objects
  return `410` so the UI can show a graceful fallback.
- Thumbnails open in a lightbox with full metadata; previous/current screenshots on a
  change event show timestamps, run status, and the visual distance.

## Config

```env
VISUAL_AHASH_THRESHOLD=5
MAX_BROWSER_CHECKS_PER_DAY=50
```
