import { describe, expect, it } from "vitest";
import {
	composeHeadline,
	parseSummaryParts,
	stripDecoration,
} from "@/lib/summary";

describe("parseSummaryParts", () => {
	it("returns the whole summary for a plain signal", () => {
		const parts = parseSummaryParts("The price rose from $19.99 to $24.99.");
		expect(parts.kind).toBe("plain");
		expect(parts.reason).toBeNull();
		expect(parts.detail).toBe("The price rose from $19.99 to $24.99.");
	});

	it("splits a triage summary into reason and detail", () => {
		const parts = parseSummaryParts(
			"[AI triage] cookie banner churn (watched: prices)\nThe banner text changed.",
		);
		expect(parts.kind).toBe("triage");
		expect(parts.reason).toBe("cookie banner churn");
		expect(parts.detail).toBe("The banner text changed.");
	});

	it("splits a conditional summary", () => {
		const parts = parseSummaryParts("[Conditional] price_below 20 (threshold not met)");
		expect(parts.kind).toBe("conditional");
		expect(parts.reason).toBe("price_below 20 (threshold not met)");
		expect(parts.detail).toBe("");
	});

	it("handles a legacy triage summary without a detail line", () => {
		const parts = parseSummaryParts("[AI triage] banner churn (watched: x)");
		expect(parts.kind).toBe("triage");
		expect(parts.reason).toBe("banner churn");
		expect(parts.detail).toBe("");
	});

	it("handles empty input", () => {
		expect(parseSummaryParts(null)).toEqual({ kind: "plain", reason: null, detail: "" });
	});
});

describe("stripDecoration", () => {
	it("removes the legacy title prefix and impact suffix", () => {
		expect(stripDecoration("Pricing up: the price rose (impact: high)", "Pricing up")).toBe(
			"the price rose",
		);
	});

	it("keeps a prefix that does not match the title", () => {
		expect(stripDecoration("Something else: text", "Pricing up")).toBe("Something else: text");
	});

	it("removes a trailing impact suffix", () => {
		expect(stripDecoration("Body text (impact: low)")).toBe("Body text");
	});
});

describe("composeHeadline", () => {
	it("prefers the triage reason", () => {
		const parts = parseSummaryParts("[AI triage] banner churn\nBody");
		expect(composeHeadline(parts, "Title")).toBe("banner churn");
	});

	it("combines title and detail for a signal", () => {
		const parts = parseSummaryParts("The price rose.");
		expect(composeHeadline(parts, "Pricing up")).toBe("Pricing up — The price rose.");
	});

	it("does not repeat the title when it is already in the text", () => {
		const parts = parseSummaryParts("Pricing up: The price rose.");
		expect(composeHeadline(parts, "Pricing up")).toBe("Pricing up: The price rose.");
	});
});
