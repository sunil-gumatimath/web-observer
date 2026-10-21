# Monitoring modes

Web Observer supports **9 monitoring modes**. The authoritative list lives in
`backend/app/models/entities.py` (`MonitorMode` / `MONITOR_MODES`); the UI
mirror is `frontend/src/lib/modes.ts` (`MONITOR_MODE_OPTIONS`). A unit test
(`backend/tests/test_monitor_modes_regression.py` and
`frontend/src/lib/modes.test.ts`) guards that both stay in sync.

Every mode answers the same question — *what did you extract from the URL, and
what counts as a change?* — but they extract different things and diff them
differently.

---

## Mode matrix

| Mode | Extracts | Diff shape | Fetch path | `css_selector` | Value chart | Thresholds |
| ---- | -------- | ---------- | ---------- | -------------- | ----------- | ---------- |
| `page_content` | Whole page rendered to markdown | Line-by-line unified diff | HTTP or browser | optional | no | `percent_change`, `min_diff_chars`, `regex_must_match`, `regex_must_not_match` |
| `site_links` | Sitemap URL inventory | Item set (added / removed URLs) | **plain HTTP only** | no | no | `list_min_added`, `list_min_removed` |
| `product_price` | First price-like token, normalized (e.g. `USD 19.99`) | Value change | HTTP or browser | optional (price scope) | **yes** | `price_below`, `price_above`, `percent_change` |
| `list_items` | CSS-selector matches as `[text](href)` | Item set (added / removed) | HTTP or browser | **required** | no | `list_min_added`, `list_min_removed` |
| `json_field` | One value at a JSONPath-style path | Value change | HTTP or browser | **required** (JSON path) | **yes** | `value_below`, `value_above`, `percent_change` |
| `rss_feed` | RSS/Atom item list, matched on GUID/link | Item set (added / removed entries) | **plain HTTP only** | no | no | `list_min_added`, `list_min_removed` |
| `readme` | `README.md` of a GitHub repo, default branch | Line-by-line markdown diff | **plain HTTP only** | no | no | common only |
| `visual` | Full-page screenshot, perceptual hash | Screenshot similarity (pHash) | **browser only** | optional (clip region) | no | common only (no regex filters) |
| `security_scan` | Cloudflare URL Scanner verdict + technology inventory | Item set (added / removed facts) | **Cloudflare edge only** | no | no | common + `list_min_added`, `list_min_removed` |

**"plain HTTP only"** means `js_required` is rejected at the schema layer
(`backend/app/schemas.py`) and the workers bounce the job back onto the HTTP
queue as defence in depth. Playwright would snapshot the wrong content for a
sitemap, a feed, a README file, or an edge-rendered scan.

### Thresholds available to every mode

These six keys are accepted on any monitor, on top of the per-mode keys above
(`backend/app/services/conditional.py`, `frontend/src/lib/thresholds.ts`):

| Key | Effect |
| --- | ------ |
| `min_diff_chars` | Minimum size of the change. For `visual` it means the **perceptual distance** (pHash, or aHash for legacy snapshots) instead of a character count. |
| `regex_must_match` | The new content must match this pattern, otherwise the change is held back. |
| `regex_must_not_match` | If the new content matches this pattern, the change is held back. |
| `cooldown_minutes` | Quiet period after a signal alert — no further notifications for this monitor. |
| `flap_window_minutes` + `flap_max_alerts` | Flapping guard: when this many signal changes fire inside the window, alerts are bundled. |

Two caveats:

- The regex filters are **not offered for `visual` mode** in the UI — a
  screenshot's content is a hash, so a content regex can never match it.
- `security_scan` gets `list_min_added` / `list_min_removed` from the backend
  (it is in `LIST_DIFF_MODES`), but the Threshold Editor does not surface them
  for that mode yet. Set them via the API if you need them.

---

## The modes in detail

### `page_content`

The default. Fetches the page, converts the HTML to markdown, drops the noise
(ignored selectors and ignore regexes configured per monitor), and diffs the
result line by line.

- Use **Ignore selectors** / **Ignore regexes** to hide cookie banners, ad
  slots, and CSRF tokens so they don't fire false alerts.
- Enable `js_required` for SPAs — the page is then rendered in a real browser
  (Playwright) and the **browser worker** must be running.
- Thresholds: `percent_change` (share of the page that changed),
  `min_diff_chars`, and the two regex filters.

### `site_links`

Fetches a sitemap and watches the URL inventory. Added and removed URLs are
reported as a set diff, so re-ordering the sitemap is not a change.

- Point the monitor at `https://example.com/sitemap.xml`.
- `js_required` is rejected.

### `product_price`

Scans the page for the first price-like token and normalizes it
(`$19.99` → `USD 19.99`). Reports the price and currency when either changes.

- Defaults to a **daily** schedule — price pages rarely move faster than that
  and each browser check burns quota.
- Use the optional CSS selector to scope the price search
  (e.g. `#price, .product-price`) and avoid picking up a cross-sell widget.
- Gets a **value-history chart** on the monitor page.
- Thresholds: `price_below`, `price_above`, `percent_change`.

### `list_items`

Watches a list of elements (blog entries, changelog items, headings) and
reports what was added or removed, as clickable links.

- The **CSS selector is required** (e.g. `.post-list li a`). Use the
  point-and-click **selector picker** on the New/Edit monitor form to write it
  for you.
- Thresholds: `list_min_added`, `list_min_removed` — e.g. alert only when at
  least 3 entries were added.

### `json_field`

Watches one value inside a JSON response.

- The **JSON path is required** (e.g. `$.data.price`, `$.results[0].status`).
- The URL must return JSON.
- Gets a **value-history chart**.
- Thresholds: `value_below`, `value_above`, `percent_change`.

### `rss_feed`

Fetches an RSS or Atom feed and watches the item list. Entries are matched on
GUID (falling back to link), so a feed that re-orders or re-dates existing
entries is not a change.

- `js_required` is rejected.

### `readme`

Watches the `README.md` of a GitHub repository on its default branch.

- Accepts the `owner/repo` shorthand (`vercel/next.js`) or a full GitHub URL.
- Diffs render as GitHub-style markdown, so code fences and nested lists stay
  intact.
- The fetcher hits the GitHub API first (1 request, resolves the default
  branch) and falls back to capped raw probes.
- `js_required` is rejected.

### `visual`

Renders the page in a browser and compares screenshots perceptually.

- Forces `js_required` and `screenshots_enabled` — the browser worker is
  required.
- Comparison uses a **DCT pHash** (256-bit, `VISUAL_PHASH_THRESHOLD=8` bits of
  hamming distance). Snapshots captured before the pHash path existed still use
  the legacy 64-bit aHash (`VISUAL_AHASH_THRESHOLD=5`).
- The optional CSS selector clips the comparison to one region (e.g. `#hero`),
  which is the cheapest way to stop a rotating banner from firing alerts.
- Needs **2 signal changes** before the before/after slider can render.

### `security_scan`

Runs the URL through the **Cloudflare URL Scanner** on Cloudflare's edge and
watches the security verdict.

- Requires server-side credentials: `CLOUDFLARE_ACCOUNT_ID` and
  `CLOUDFLARE_URLSCANNER_TOKEN`. Without a token the check fails with a clear
  error (it never silently passes).
- The digest is one fact per line — `malicious=`, `categories=`, `tags=`,
  `task.status=`, `task.apexDomain=`, `certificate=`, `server=`, `asn=`, and
  `tech=` — so the diff shows exactly which fact moved.
- Volatile counters (cookie counts, link counts, performance metrics) are
  deliberately excluded so an unchanged page does not alert on noise.
- `js_required` is rejected — the scan happens on Cloudflare's edge.
- Keep the interval **daily or slower**: each check is a real edge scan.

---

## Choosing a mode

| If you want to watch... | Use |
| ----------------------- | --- |
| Any page's text | `page_content` |
| A pricing page | `product_price` |
| A JSON API's field | `json_field` |
| A blog index or changelog | `list_items` |
| A site's URL inventory | `site_links` |
| A feed | `rss_feed` |
| A repo's docs | `readme` |
| A layout or image change | `visual` |
| A site's security posture | `security_scan` |

## Related

- [docs/architecture.md](../architecture.md) — where each mode is dispatched
- [docs/roadmap.md](../roadmap.md) — planned mode work (PDF/documents, bounding-box crop)
- [docs/local-dev.md](../local-dev.md) — running the workers each mode needs
