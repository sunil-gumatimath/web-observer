# Monitoring modes

Web Observer supports **10 monitoring modes**. The authoritative list lives in
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
| `page_content` | Main content rendered to markdown, falling back to the whole page | Line-by-line unified diff | HTTP or browser | optional | no | `percent_change`, `min_diff_chars`, `regex_must_match`, `regex_must_not_match` |
| `site_links` | Sitemap URL inventory | Item set (added / removed URLs) | **plain HTTP only** | no | no | `list_min_added`, `list_min_removed` |
| `product_price` | First price-like token, normalized (e.g. `USD 19.99`) | Value change | HTTP or browser | optional (price scope) | **yes** | `price_below`, `price_above`, `percent_change` |
| `list_items` | CSS-selector matches as `[text](href)` | Item set (added / removed) | HTTP or browser | **required** | no | `list_min_added`, `list_min_removed` |
| `json_field` | One value at a JSONPath-style path | Value change | HTTP or browser | **required** (JSON path) | **yes** | `value_below`, `value_above`, `percent_change` |
| `rss_feed` | RSS/Atom item list, matched on GUID/link | Item set (added / removed entries) | **plain HTTP only** | no | no | `list_min_added`, `list_min_removed` |
| `readme` | `README.md` of a GitHub repo (default branch or `/tree/<branch>`) | Line-by-line markdown diff | **plain HTTP only** | no | no | common only |
| `visual` | Full-page screenshot, perceptual hash | Screenshot similarity (pHash) | **browser only** | optional (clip region) | no | common only (no regex filters) |
| `security_scan` | Cloudflare URL Scanner verdict + technology inventory | Item set (added / removed facts) | **Cloudflare edge only** | no | no | common + `list_min_added`, `list_min_removed` |
| `html_meta` | Title, allow-listed meta tags, canonical/alternate links, JSON-LD types, external script URLs | Item set (added / removed facts) | **plain HTTP only** | no | no | common + `list_min_added`, `list_min_removed` |

**"plain HTTP only"** means `js_required` is rejected at the schema layer
(`backend/app/schemas.py`) and the workers bounce the job back onto the HTTP
queue as defence in depth. Playwright would snapshot the wrong content for a
sitemap, a feed, a README file, or an edge-rendered scan.

### Thresholds available to every mode

These six keys are accepted on any monitor, on top of the per-mode keys above
(`backend/app/services/conditional.py`, `frontend/src/lib/thresholds.ts`):

| Key | Effect |
| --- | ------ |
| `min_diff_chars` | Minimum size of the change. For `visual` it means the **perceptual distance** (pHash, or aHash for legacy snapshots) instead of a character count — and it *is* the comparison threshold, so a larger value means a coarser comparison (fewer alerts), the opposite direction to the other modes. |
| `regex_must_match` | The new content must match this pattern, otherwise the change is held back. |
| `regex_must_not_match` | If the new content matches this pattern, the change is held back. |
| `cooldown_minutes` | Quiet period after a signal alert — no further notifications for this monitor. |
| `flap_window_minutes` + `flap_max_alerts` | Flapping guard: when this many signal changes fire inside the window, alerts are bundled. |

One caveat:

- The regex filters are **not offered for `visual` mode** in the UI — a
  screenshot's content is a hash, so a content regex can never match it.
- For `visual`, `min_diff_chars` is a *perceptual distance* threshold, not a
  minimum edit size, so it runs in the opposite direction: a **larger** value
  tolerates more visual drift before alerting (fewer alerts), while a smaller
  value makes the comparison more sensitive. Without it, the global
  `VISUAL_AHASH_THRESHOLD` / `VISUAL_PHASH_THRESHOLD` defaults apply.
---

## The modes in detail

### `page_content`

The default. Fetches the page, detects and converts its main content to
markdown, and falls back to the whole body when main content cannot be
identified. It then drops the noise (ignored selectors and ignore regexes
configured per monitor) and diffs the result line by line. Changes outside
detected main content are not watched.

- Use **Ignore selectors** / **Ignore regexes** to hide cookie banners, ad
  slots, and CSRF tokens so they don't fire false alerts.
- Enable `js_required` for SPAs — the page is then rendered in a real browser
  (Playwright) and the **browser worker** must be running.
- Thresholds: `percent_change` (edited characters as a share of the longer
  snapshot; same-length rewrites count),
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
  The selector (and any ignore selectors) always win over the optional
  Context.dev structured-price provider — with a selector configured the
  price is read locally first and the provider is only consulted if that
  finds nothing, so scoping keeps working when the provider key is set.
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

Watches the `README.md` of a GitHub repository — on the default branch, or
pinned to a specific one via `/tree/<branch>` / `/blob/<branch>/...` URLs.

- Accepts the `owner/repo` shorthand (`vercel/next.js`) or a full GitHub URL.
- Diffs render as GitHub-style markdown, so code fences and nested lists stay
  intact.
- The fetcher hits the GitHub API first (1 request, `ref`-pinned to the
  parsed branch hint when there is one, else the repo's default branch) and
  falls back to raw probes bounded by a wall-clock budget so a dead CDN can
  never push the fetch past the worker's time limit.
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
- The change detail shows the two compared runs as a **before/after slider**
  (`screenshots/<monitor_id>/<run_id>.png`) with the perceptual-hash summary in
  a collapsible panel, so you see the pixels that actually moved, not just the
  latest two screenshots. One detected change is enough: the baseline comes from
  the change's `previous_snapshot_id` run, falling back to the preceding
  succeeded run when the monitor detail page has only one change recorded.

### `security_scan`

Runs the URL through the **Cloudflare URL Scanner** on Cloudflare's edge and
watches the security verdict.

- Requires server-side credentials: `CLOUDFLARE_ACCOUNT_ID` and
  `CLOUDFLARE_URLSCANNER_TOKEN`. Without a token the check fails with a clear
  error (it never silently passes).
- Failures are surfaced with filterable error codes: `scan_not_configured`
  (no token), `scan_rejected` (the Scanner refused/aborted the target —
  status `failed`/`aborted`/`rejected`/`error`), `scan_task_error` (Cloudflare
  reported an unsuccessful scan, e.g. code 5021 "hostname was recently
  scanned"), `scan_error` (transient submit/result API or transport failure),
  and `read_timeout` (the scan did not finish in time).
- The digest is one fact per line — `malicious=`, `categories=`, `tags=`,
  `task.status=`, `task.apexDomain=`, `certificate=`, `server=`, `asn=`, and
  `tech=` — so the diff shows exactly which fact moved.
- Volatile counters (cookie counts, link counts, performance metrics) are
  deliberately excluded so an unchanged page does not alert on noise.
- `js_required` is rejected — the scan happens on Cloudflare's edge.
- Keep the interval **daily or slower**: each check is a real edge scan.

### `html_meta`

Watches the **code-level** facts that `page_content` deliberately ignores.

- Extracts `<title>`, `html lang`, a small allow-list of meta tags (description,
  robots, OpenGraph, Twitter cards, theme colour, etc.), canonical and hreflang
  links, schema.org `@type` values from JSON-LD, and external `<script src>`
  URLs.
- Each fact is one `key: value` line, diffed as an item set, so alerts read
  "meta robots removed" or "script src added" instead of a wall of HTML.
- Query strings and fragments are stripped from URLs so analytics tokens,
  cache-busting parameters and build ids do not cause false alerts. The one
  exception is the preview images (`og:image`, `twitter:image`): their query
  string is kept, because CDN resize/format params and signed-URL tokens
  change the image that is actually served, so a preview swap that only
  differs by query is a real change.
- Unlisted meta tags (CSRF tokens, build ids, arbitrary vendor tags) are
  ignored by design.
- Fetched over plain HTTP; `js_required` is rejected. Use it for SEO checks,
  tracking-script changes and compliance pages.
- Facts are bounded: at most 5 canonicals, 40 hreflang alternates, 20 JSON-LD
  types and 50 script URLs, with a total cap of 150 facts. The per-kind caps
  are applied before the total cap so a busy page cannot silently evict
  script or meta facts.

---

## Optional Context.dev provider (fetch failover)

Set `CONTEXT_DEV_API_KEY` in `backend/.env` (server-side only) to enable three
opt-in upgrades. With no key, every mode behaves exactly as documented above.

| Mode | Upgrade | Trigger |
| ---- | ------- | ------- |
| `product_price` | Structured price/currency from Context.dev `formats.product` instead of the first price-like regex match | Every check when the key is set **and the monitor has no price selector / ignore selectors** — an explicit scope is always honoured locally first; falls back to local regex on any provider error |
| `site_links` | URL inventory from the Map URLs endpoint when no sitemap exists | Only after the normal sitemap discovery fails; a non-empty result replaces the `no_sitemap` error |
| `page_content` / `visual` | Markdown or screenshot capture from Context.dev | Only when the local fetch/capture fails with `bot_challenge`, `http_error` (401/403/429), `read_timeout`, or a Playwright error |

The provider is best-effort: failures never fail a check that would have worked
locally, and the original local error is preserved when the fallback also fails.
Each successful fallback spends Context.dev credits (1 per scrape / screenshot,
plus 1 when the product extraction succeeds), so keep schedules sane — a
hourly monitor is roughly 720 credits/month.

## Fetch reliability and previews

You can add any public `http(s)` URL as a monitor, but a monitor only produces a preview after a
**successful** check. The preview is a stored snapshot from that run, not a live view of the site.

- Public HTML, RSS/sitemap, README, JSON and price pages generally work over plain HTTP.
- JS-heavy pages need `js_required` (or `visual` mode) and a working local Playwright Chromium install.
- Bot protections (Cloudflare/ Turnstile challenges), login-only and paywalled pages can make a check
  fail with `bot_challenge` or `http_error`; no new preview is produced. Product Hunt is a common
  example. Enabling browser mode may help, but it does not bypass authentication.
- Private/loopback/link-local addresses are blocked by the SSRF guard on purpose, so `localhost`
  and LAN URLs cannot be monitored.
- The first successful run is a baseline; later successful runs create change events and update the
  preview.

If a check fails, open the monitor's run history to see the error code before debugging the preview.

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
| Code-level HTML/meta changes | `html_meta` |

## Related

- [docs/architecture.md](../architecture.md) — where each mode is dispatched
- [docs/local-dev.md](../local-dev.md) — running the workers each mode needs
