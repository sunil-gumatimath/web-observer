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

## Config

```env
VISUAL_AHASH_THRESHOLD=5
MAX_BROWSER_CHECKS_PER_DAY=50
```
