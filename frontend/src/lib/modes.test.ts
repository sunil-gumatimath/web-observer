import { describe, expect, it } from "vitest";
import {
	LIST_DIFF_MODES,
	MONITOR_MODE_OPTIONS,
	PLAIN_HTTP_MODES,
	SITEMAP_IMPORT_MODES,
	VALUE_HISTORY_MODES,
	modeLabel,
	needsJs,
	requiresSelector,
	showsIgnore,
	showsSelector,
} from "@/lib/modes";
import type { MonitorMode } from "@/lib/types";

const ALL_MODES: MonitorMode[] = [
	"page_content",
	"site_links",
	"product_price",
	"list_items",
	"json_field",
	"rss_feed",
	"readme",
	"visual",
];

describe("MONITOR_MODE_OPTIONS", () => {
	it("covers every monitor mode exactly once", () => {
		const values = MONITOR_MODE_OPTIONS.map((o) => o.value);
		expect(new Set(values).size).toBe(values.length);
		expect([...values].sort()).toEqual([...ALL_MODES].sort());
	});

	it("gives every mode a label, an option label and a hint", () => {
		for (const o of MONITOR_MODE_OPTIONS) {
			expect(o.label.length).toBeGreaterThan(0);
			expect(o.optionLabel.length).toBeGreaterThan(0);
			expect(o.hint.length).toBeGreaterThan(0);
		}
	});
});

describe("modeLabel", () => {
	it("maps a mode to its human label", () => {
		expect(modeLabel("rss_feed")).toBe("RSS feed");
		expect(modeLabel("readme")).toBe("GitHub README");
		expect(modeLabel("visual")).toBe("Visual diff");
	});

	it("falls back to the raw value for unknown modes", () => {
		expect(modeLabel("mystery")).toBe("mystery");
	});
});

describe("needsJs", () => {
	it("is false for the plain-HTTP modes only", () => {
		expect(needsJs("site_links")).toBe(false);
		expect(needsJs("rss_feed")).toBe(false);
		expect(needsJs("readme")).toBe(false);
		expect(needsJs("page_content")).toBe(true);
		expect(needsJs("product_price")).toBe(true);
		expect(needsJs("list_items")).toBe(true);
		expect(needsJs("json_field")).toBe(true);
		expect(needsJs("visual")).toBe(true);
	});
});

describe("showsIgnore / showsSelector / requiresSelector", () => {
	it("offers ignore rules for page content only", () => {
		expect(showsIgnore("page_content")).toBe(true);
		expect(showsIgnore("list_items")).toBe(false);
	});

	it("exposes the selector field for every mode that uses css_selector", () => {
		expect(showsSelector("list_items")).toBe(true);
		expect(showsSelector("json_field")).toBe(true);
		expect(showsSelector("product_price")).toBe(true);
		expect(showsSelector("visual")).toBe(true);
		expect(showsSelector("page_content")).toBe(false);
		expect(showsSelector("site_links")).toBe(false);
		expect(showsSelector("rss_feed")).toBe(false);
		expect(showsSelector("readme")).toBe(false);
	});

	it("requires a selector only for list_items and json_field", () => {
		expect(requiresSelector("list_items")).toBe(true);
		expect(requiresSelector("json_field")).toBe(true);
		expect(requiresSelector("product_price")).toBe(false);
		expect(requiresSelector("visual")).toBe(false);
	});
});

describe("mode sets", () => {
	it("keeps the plain-HTTP set in sync with needsJs", () => {
		for (const mode of ALL_MODES) {
			expect(needsJs(mode)).toBe(!PLAIN_HTTP_MODES.includes(mode));
		}
	});

	it("treats rss_feed as a list-diff mode", () => {
		expect(LIST_DIFF_MODES).toContain("rss_feed");
		expect(LIST_DIFF_MODES).toContain("site_links");
		expect(LIST_DIFF_MODES).toContain("list_items");
	});

	it("exposes a value history only for the numeric modes", () => {
		expect(VALUE_HISTORY_MODES).toEqual(["product_price", "json_field"]);
	});

	it("offers only modes that make sense per sitemap URL", () => {
		// readme needs a GitHub repo and rss_feed needs a feed URL — neither
		// applies to a page URL discovered in a sitemap.
		expect(SITEMAP_IMPORT_MODES).not.toContain("readme");
		expect(SITEMAP_IMPORT_MODES).not.toContain("rss_feed");
		for (const mode of SITEMAP_IMPORT_MODES) {
			expect(ALL_MODES).toContain(mode);
		}
	});
});
