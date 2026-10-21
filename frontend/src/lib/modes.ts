import type { MonitorMode } from "@/lib/types";

/**
 * Single source of truth for monitor-mode UI metadata.
 *
 * The backend keeps the authoritative list in
 * `backend/app/models/entities.py` (`MonitorMode` / `MONITOR_MODES`). The
 * option list below mirrors it exactly — every mode must appear once, and the
 * `MONITOR_MODE_OPTIONS` array is what the create / edit / sitemap forms and
 * the list filter render.
 */

export type MonitorModeOption = {
	value: MonitorMode;
	/** Short label used in dropdowns and badges. */
	label: string;
	/** Longer label used inside the mode dropdowns. */
	optionLabel: string;
	/** One-line explanation shown under the dropdown. */
	hint: string;
};

export const MONITOR_MODE_OPTIONS: MonitorModeOption[] = [
	{
		value: "page_content",
		label: "Page content",
		optionLabel: "Page content (whole page text)",
		hint: "Page content: watches the whole page as text and reports any change with a line-level diff.",
	},
	{
		value: "site_links",
		label: "Site links",
		optionLabel: "Site links (sitemap URL changes)",
		hint: "Site links: watches the site's sitemap and reports added or removed URLs.",
	},
	{
		value: "product_price",
		label: "Product price",
		optionLabel: "Product price (price / currency)",
		hint: "Product price: watches the price on a product page and reports price or currency changes.",
	},
	{
		value: "list_items",
		label: "List items",
		optionLabel: "List items (e.g. blog/changelog entries)",
		hint: "List items: watches a list of elements (headlines, posts, entries) and reports what was added or removed as clickable links. Set the target CSS selector below.",
	},
	{
		value: "json_field",
		label: "JSON field",
		optionLabel: "JSON field (API / JSON responses)",
		hint: "JSON field: watches one value inside a JSON response and reports when it changes. Set the JSON path below.",
	},
	{
		value: "rss_feed",
		label: "RSS feed",
		optionLabel: "RSS feed (added or removed entries)",
		hint: "RSS feed: watches an RSS/Atom feed and reports added or removed entries, matched on GUID/link.",
	},
	{
		value: "readme",
		label: "GitHub README",
		optionLabel: "GitHub README (repo documentation)",
		hint: "README: monitors README.md on the repo's default branch (main/master). Use vercel/next.js or the full GitHub URL.",
	},
	{
		value: "visual",
		label: "Visual diff",
		optionLabel: "Visual diff (screenshot comparison)",
		hint: "Visual diff: renders the page in a browser and compares screenshots perceptually. Set an optional CSS selector to compare only part of the page.",
	},
	{
		value: "security_scan",
		label: "Security scan",
		optionLabel: "Security scan (Cloudflare URL Scanner)",
		hint: "Security scan: renders the URL on Cloudflare's edge and reports verdict/category/technology changes. Needs a free Cloudflare token on the server; keep the interval daily or slower.",
	},
];

/** Short human label for a mode (badges, filters, share pages). */
export function modeLabel(mode: string): string {
	return MONITOR_MODE_OPTIONS.find((o) => o.value === mode)?.label ?? mode;
}

/**
 * Modes that are always fetched over plain HTTP. Playwright would snapshot
 * the wrong content for them, so the JS checkbox is hidden and the backend
 * rejects `js_required` for these modes.
 */
export const PLAIN_HTTP_MODES: MonitorMode[] = ["site_links", "rss_feed", "readme", "security_scan"];

/** Modes whose diff is an item list (added / removed) rather than text lines. */
export const LIST_DIFF_MODES: MonitorMode[] = ["site_links", "list_items", "rss_feed", "security_scan"];

/** Modes that expose a value history chart. */
export const VALUE_HISTORY_MODES: MonitorMode[] = ["product_price", "json_field"];

/**
 * Modes that make sense when creating one monitor per URL discovered in a
 * sitemap. `readme` needs a GitHub repository and `rss_feed` needs a feed
 * URL — neither applies to a page URL taken from a sitemap, so offering them
 * would create monitors that fail on every check.
 */
export const SITEMAP_IMPORT_MODES: MonitorMode[] = [
	"page_content",
	"site_links",
	"product_price",
	"list_items",
	"json_field",
	"visual",
];

export function needsJs(mode: MonitorMode): boolean {
	return !PLAIN_HTTP_MODES.includes(mode);
}

export function showsIgnore(mode: MonitorMode): boolean {
	return mode === "page_content";
}

export function isReadmeMode(mode: MonitorMode): boolean {
	return mode === "readme";
}

/** Modes that use the `css_selector` column for something other than a path. */
export function showsSelector(mode: MonitorMode): boolean {
	return mode === "list_items" || mode === "json_field" || mode === "product_price" || mode === "visual";
}

/** True when the mode *requires* a css_selector (list selector / JSON path). */
export function requiresSelector(mode: MonitorMode): boolean {
	return mode === "list_items" || mode === "json_field";
}

/** Label for the css_selector input, per mode. */
export function selectorLabel(mode: MonitorMode): string {
	switch (mode) {
		case "json_field":
			return "JSON path (required for JSON field)";
		case "list_items":
			return "List CSS selector (required for List items)";
		case "product_price":
			return "Price CSS selector (optional)";
		case "visual":
			return "Clip CSS selector (optional)";
		default:
			return "CSS selector";
	}
}

/** Placeholder for the css_selector input, per mode. */
export function selectorPlaceholder(mode: MonitorMode): string {
	switch (mode) {
		case "json_field":
			return "$.data.price";
		case "list_items":
			return "article h2 a, .post-title a";
		case "product_price":
			return "#price, .product-price";
		case "visual":
			return "#hero, .pricing-table";
		default:
			return "";
	}
}

/** Helper text under the css_selector input, per mode. */
export function selectorHelp(mode: MonitorMode): string {
	switch (mode) {
		case "json_field":
			return "Path to the value to watch, e.g. $.data.price or $.results[0].status.";
		case "list_items":
			return "Select the links to track, e.g. .post-list li a.";
		case "product_price":
			return "Restrict the price search to these elements. Leave empty to scan the whole page.";
		case "visual":
			return "Compare only this element instead of the whole page, e.g. #hero. Leave empty for the full page.";
		default:
			return "";
	}
}
