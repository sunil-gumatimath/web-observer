import { describe, expect, it } from "vitest";
import { formatTags, parseTagInput } from "@/lib/tags";

describe("parseTagInput", () => {
	it("splits, lowercases, dedupes", () => {
		expect(parseTagInput("Pricing, pricing , competitors,, ")).toEqual([
			"pricing",
			"competitors",
		]);
	});

	it("caps at ten tags", () => {
		const many = Array.from({ length: 12 }, (_, i) => `t${i}`).join(",");
		expect(parseTagInput(many)).toHaveLength(10);
	});
});

describe("formatTags", () => {
	it("joins with commas", () => {
		expect(formatTags(["a", "b"])).toBe("a, b");
		expect(formatTags(null)).toBe("");
	});
});
