import { describe, expect, it } from "vitest";
import {
	applyNumericDraft,
	applyPatternDraft,
	isEmptyConfig,
	isValidRegex,
	keysForMode,
	parseNumericDraft,
	toDrafts,
} from "@/lib/thresholds";

describe("keysForMode", () => {
	it("gives price bounds only to product_price", () => {
		expect(keysForMode("product_price")).toEqual([
			"price_below",
			"price_above",
			"percent_change",
			"min_diff_chars",
			"regex_must_match",
			"regex_must_not_match",
		]);
	});

	it("gives percent_change to json_field and page_content", () => {
		for (const mode of ["json_field", "page_content"] as const) {
			const keys = keysForMode(mode);
			expect(keys).toContain("percent_change");
			expect(keys).not.toContain("price_below");
			expect(keys).not.toContain("list_min_added");
		}
	});

	it("gives list minimums to list-like modes", () => {
		for (const mode of ["list_items", "site_links", "rss_feed"] as const) {
			const keys = keysForMode(mode);
			expect(keys).toContain("list_min_added");
			expect(keys).toContain("list_min_removed");
			expect(keys).not.toContain("percent_change");
		}
	});

	it("always includes the common fields", () => {
		for (const mode of ["readme", "visual"] as const) {
			expect(keysForMode(mode)).toEqual([
				"min_diff_chars",
				"regex_must_match",
				"regex_must_not_match",
			]);
		}
	});
});

describe("parseNumericDraft", () => {
	it("parses floats and ints", () => {
		expect(parseNumericDraft("49.99", false)).toBe(49.99);
		expect(parseNumericDraft("3", true)).toBe(3);
	});

	it("rejects non-numeric and partial input", () => {
		expect(parseNumericDraft("", false)).toBeNull();
		expect(parseNumericDraft("1.", false)).toBe(1); // Number("1.") === 1, still committable
		expect(parseNumericDraft("abc", false)).toBeNull();
		expect(parseNumericDraft("12px", true)).toBeNull();
	});

	it("rejects fractions for integer fields", () => {
		expect(parseNumericDraft("2.5", true)).toBeNull();
	});
});

describe("isValidRegex", () => {
	it("accepts valid patterns and rejects broken ones", () => {
		expect(isValidRegex("price:\\s+\\$\\d+")).toBe(true);
		expect(isValidRegex("")).toBe(true);
		expect(isValidRegex("([unclosed")).toBe(false);
	});
});

describe("applyNumericDraft", () => {
	it("commits valid numbers into the config", () => {
		expect(applyNumericDraft("price_below", "49.99", false, null)).toEqual({
			price_below: 49.99,
		});
		expect(
			applyNumericDraft("list_min_added", "2", true, { price_below: 10 }),
		).toEqual({ price_below: 10, list_min_added: 2 });
	});

	it("keeps intermediate input local", () => {
		expect(applyNumericDraft("price_below", "abc", false, null)).toBeNull();
		expect(applyNumericDraft("list_min_added", "2.5", true, null)).toBeNull();
	});

	it("deletes the key on blank, no-ops when already absent", () => {
		expect(
			applyNumericDraft("price_below", "  ", false, { price_below: 10 }),
		).toEqual({});
		expect(applyNumericDraft("price_below", "", false, null)).toBeNull();
		expect(
			applyNumericDraft("price_below", "", false, { percent_change: 5 }),
		).toBeNull();
	});

	it("no-ops when the value is unchanged", () => {
		expect(
			applyNumericDraft("price_below", "10", false, { price_below: 10 }),
		).toBeNull();
	});
});

describe("applyPatternDraft", () => {
	it("commits valid patterns, drops invalid ones", () => {
		expect(applyPatternDraft("regex_must_match", "sale", null)).toEqual({
			regex_must_match: "sale",
		});
		expect(applyPatternDraft("regex_must_match", "([bad", null)).toBeNull();
	});

	it("deletes the key on blank", () => {
		expect(
			applyPatternDraft("regex_must_match", "", { regex_must_match: "sale" }),
		).toEqual({});
	});
});

describe("toDrafts / isEmptyConfig", () => {
	it("round-trips configs to editable strings", () => {
		expect(toDrafts(null).price_below).toBe("");
		expect(
			toDrafts({ price_below: 49.99, regex_must_match: "sale" }).price_below,
		).toBe("49.99");
	});

	it("detects empty configs", () => {
		expect(isEmptyConfig(null)).toBe(true);
		expect(isEmptyConfig({})).toBe(true);
		expect(isEmptyConfig({ price_below: 10 })).toBe(false);
	});
});
