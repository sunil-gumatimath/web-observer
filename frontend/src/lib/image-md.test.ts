import { describe, expect, it } from "vitest";
import { readmeAssetBase, resolveMarkdownAssetUrl } from "@/lib/image-md";

describe("readmeAssetBase", () => {
	it("builds a raw.githubusercontent base for owner/repo shorthand URLs", () => {
		expect(readmeAssetBase("https://github.com/vercel/next.js")).toBe(
			"https://raw.githubusercontent.com/vercel/next.js/HEAD/",
		);
	});

	it("uses the pinned branch when the monitor URL names one", () => {
		expect(readmeAssetBase("https://github.com/vercel/next.js/tree/canary")).toBe(
			"https://raw.githubusercontent.com/vercel/next.js/canary/",
		);
	});

	it("returns null for non-GitHub URLs", () => {
		expect(readmeAssetBase("https://example.com/owner/repo")).toBeNull();
		expect(readmeAssetBase(null)).toBeNull();
	});
});

describe("resolveMarkdownAssetUrl", () => {
	it("keeps absolute http(s) URLs", () => {
		expect(resolveMarkdownAssetUrl("https://cdn.example.com/a.png")).toBe(
			"https://cdn.example.com/a.png",
		);
	});

	it("resolves relative paths against the repo base", () => {
		expect(
			resolveMarkdownAssetUrl(
				"docs/logo.png",
				"https://raw.githubusercontent.com/vercel/next.js/HEAD/",
			),
		).toBe("https://raw.githubusercontent.com/vercel/next.js/HEAD/docs/logo.png");
	});

	it("rejects unsafe schemes and empty sources", () => {
		expect(resolveMarkdownAssetUrl("javascript:alert(1)")).toBeNull();
		expect(resolveMarkdownAssetUrl("")).toBeNull();
		expect(resolveMarkdownAssetUrl("a.png", null)).toBeNull();
	});
});
