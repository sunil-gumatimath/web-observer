import { describe, expect, it } from "vitest";
import {
	clampIndex,
	filterMonitors,
	filterRoutes,
} from "@/lib/palette";
import { parseImpact, stripImpact } from "@/components/ui";

const MONITORS = [
	{ id: "1", name: "Hacker News", url: "https://news.ycombinator.com", mode: "page_content" },
	{ id: "2", name: "Free AI Credits", url: "https://example.com/ai", mode: "visual" },
	{ id: "3", name: "WebObserver", url: "https://github.com/o/r", mode: "readme" },
];

const ROUTES = [
	{ href: "/dashboard", label: "Go to Dashboard", hint: "overview" },
	{ href: "/monitors/new", label: "New monitor", hint: "create" },
];

describe("filterMonitors", () => {
	it("returns the first page unfiltered", () => {
		expect(filterMonitors(MONITORS, "")).toHaveLength(3);
		expect(filterMonitors(MONITORS, "   ")).toHaveLength(3);
	});

	it("matches name, url, and mode case-insensitively", () => {
		expect(filterMonitors(MONITORS, "hacker").map((m) => m.id)).toEqual(["1"]);
		expect(filterMonitors(MONITORS, "GITHUB").map((m) => m.id)).toEqual(["3"]);
		expect(filterMonitors(MONITORS, "visual").map((m) => m.id)).toEqual(["2"]);
	});

	it("caps results at the limit", () => {
		const many = Array.from({ length: 10 }, (_, i) => ({
			id: String(i),
			name: `Monitor ${i}`,
			url: "https://example.com",
			mode: "page_content",
		}));
		expect(filterMonitors(many, "", 6)).toHaveLength(6);
	});
});

describe("filterRoutes", () => {
	it("matches label and hint", () => {
		expect(filterRoutes(ROUTES, "")).toHaveLength(2);
		expect(filterRoutes(ROUTES, "create").map((r) => r.href)).toEqual([
			"/monitors/new",
		]);
		expect(filterRoutes(ROUTES, "zzz")).toHaveLength(0);
	});
});

describe("clampIndex", () => {
	it("keeps Enter on a valid item when the list shrinks", () => {
		expect(clampIndex(5, 3)).toBe(2);
		expect(clampIndex(-1, 3)).toBe(0);
		expect(clampIndex(1, 3)).toBe(1);
		expect(clampIndex(0, 0)).toBe(0);
	});
});

describe("impact helpers", () => {
	it("parses and strips the impact suffix", () => {
		expect(parseImpact("Summary text (impact: high)")).toBe("high");
		expect(parseImpact("No suffix here")).toBeNull();
		expect(parseImpact(null)).toBeNull();
		expect(stripImpact("Summary text (impact: high)")).toBe("Summary text");
		expect(stripImpact("Plain")).toBe("Plain");
	});
});
