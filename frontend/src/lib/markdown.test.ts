import { describe, expect, it } from "vitest";
import { htmlToMarkdown } from "@/lib/markdown";

describe("htmlToMarkdown", () => {
	it("converts img tags to markdown images", () => {
		expect(htmlToMarkdown('<img src="https://x.dev/a.png" alt="Logo">')).toBe(
			"![Logo](https://x.dev/a.png)",
		);
	});

	it("converts anchor tags to markdown links", () => {
		expect(htmlToMarkdown('<a href="https://x.dev">Docs</a>')).toBe(
			"[Docs](https://x.dev)",
		);
	});

	it("drops layout tags but keeps their text", () => {
		expect(htmlToMarkdown('<p align="center">Hello</p>')).toBe("Hello");
	});

	it("removes html comments", () => {
		expect(htmlToMarkdown("a<!-- hidden -->b")).toBe("ab");
	});

	it("leaves fenced code blocks untouched", () => {
		const md = ["```html", "<div>not a tag</div>", "<img src=\"x.png\">", "```"].join("\n");
		expect(htmlToMarkdown(md)).toBe(md);
	});

	it("keeps inline code untouched", () => {
		const md = "use `<pkg>` here";
		expect(htmlToMarkdown(md)).toBe(md);
	});
});
