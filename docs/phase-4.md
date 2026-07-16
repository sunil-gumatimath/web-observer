# Phase 4 — Structured & Visual Monitoring

## Modes

| Mode | Input | Extract | Worker |
|------|--------|---------|--------|
| `whole_page` | HTML | Normalized page text | HTTP (or browser if `js_required`) |
| `css_selector` | HTML + CSS | Section text | HTTP / browser |
| `json_field` | JSON body + path | Single field / object (stable JSON) | HTTP |
| `list_items` | JSON array path **or** HTML CSS for items | Ordered list; diffs added/removed | HTTP / browser |
| `visual` | Page URL + optional region CSS | Screenshot PNG + aHash | **Browser always** |

`css_selector` column is reused as:

- CSS selector (`css_selector`, `list_items` HTML, `visual` region)
- JSON path (`json_field`, `list_items` JSON) e.g. `$.items` or `$.product.price`

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
