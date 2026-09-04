import { describe, expect, it } from "vitest";
import {
	activityFromServer,
	bucketActivity,
	categoryTotals,
	fallbackView,
	formatDayLabel,
	peakDay,
	previousWindowTotal,
	trendPct,
} from "@/lib/activity";
import type { ChangeActivity } from "@/lib/types";

const NOW = new Date("2026-09-03T12:00:00Z");

function ago(hours: number): string {
	return new Date(NOW.getTime() - hours * 3_600_000).toISOString();
}

function serverResponse(): ChangeActivity {
	return {
		days: 6,
		total: 7,
		start_date: "2026-08-29",
		end_date: "2026-09-03",
		counts: [1, 0, 1, 1, 2, 2],
		buckets: [
			{ date: "2026-08-29", count: 1, by_category: { pricing: 1 } },
			{ date: "2026-08-30", count: 0, by_category: {} },
			{ date: "2026-08-31", count: 1, by_category: { content: 1 } },
			{ date: "2026-09-01", count: 1, by_category: { pricing: 1 } },
			{ date: "2026-09-02", count: 2, by_category: { pricing: 1, content: 1 } },
			{ date: "2026-09-03", count: 2, by_category: { uncategorized: 2 } },
		],
		categories: ["pricing", "content", "uncategorized"],
	};
}

describe("bucketActivity (client fallback)", () => {
	it("returns 14 empty buckets when nothing changed", () => {
		const a = bucketActivity([], NOW);
		expect(a.days).toHaveLength(14);
		expect(a.total).toBe(0);
		expect(a.fromServer).toBe(false);
		expect(a.days.every((d) => d.total === 0)).toBe(true);
	});

	it("buckets today vs yesterday correctly", () => {
		const a = bucketActivity(
			[
				{ latest_change: { created_at: ago(2) } },
				{ latest_change: { created_at: ago(5) } },
				{ latest_change: { created_at: ago(26) } },
			],
			NOW,
		);
		expect(a.days[13].total).toBe(2); // today
		expect(a.days[12].total).toBe(1); // yesterday
		expect(a.total).toBe(3);
	});

	it("ignores missing timestamps and future/out-of-range dates", () => {
		const a = bucketActivity(
			[
				{},
				{ latest_change: null },
				{ latest_change: { created_at: ago(24 * 20) } }, // 20 days ago
				{
					latest_change: {
						created_at: new Date(NOW.getTime() + 3_600_000).toISOString(),
					},
				}, // future
				{ latest_change: { created_at: "not-a-date" } },
			],
			NOW,
		);
		expect(a.total).toBe(0);
	});

	it("buckets on UTC day boundaries regardless of local timezone", () => {
		const a = bucketActivity(
			[
				{ latest_change: { created_at: "2026-09-03T00:30:00Z" } },
				{ latest_change: { created_at: "2026-09-02T23:30:00Z" } },
			],
			NOW,
		);
		expect(a.days[13].total).toBe(1);
		expect(a.days[12].total).toBe(1);
		expect(a.total).toBe(2);
	});

	it("labels run oldest-first ending today", () => {
		expect(formatDayLabel("2026-09-03")).toBe(
			new Date("2026-09-03T12:00:00Z").toLocaleDateString(undefined, {
				month: "short",
				day: "numeric",
			}),
		);
	});
});

describe("activityFromServer", () => {
	it("slices the trailing window and keeps the breakdown", () => {
		const a = activityFromServer(serverResponse(), 3);
		expect(a.windowDays).toBe(3);
		expect(a.fromServer).toBe(true);
		expect(a.days.map((d) => d.date)).toEqual(["2026-09-01", "2026-09-02", "2026-09-03"]);
		expect(a.total).toBe(5);
		expect(a.days[1].byCategory).toEqual({ pricing: 1, content: 1 });
		expect(a.categories).toEqual(["pricing", "content", "uncategorized"]);
	});

	it("defaults to the full response range", () => {
		const a = activityFromServer(serverResponse());
		expect(a.days).toHaveLength(6);
		expect(a.total).toBe(7);
	});
});

describe("previousWindowTotal / trendPct", () => {
	it("splits a double-width response into prior vs current", () => {
		expect(previousWindowTotal(serverResponse(), 3)).toBe(2); // 1+0+1
		expect(previousWindowTotal(serverResponse(), 4)).toBe(null); // needs 8 days
	});

	it("computes rounded percent change", () => {
		expect(trendPct(5, 2)).toBe(150);
		expect(trendPct(1, 2)).toBe(-50);
		expect(trendPct(5, 0)).toBe(null);
		expect(trendPct(5, null)).toBe(null);
	});
});

describe("peakDay / categoryTotals", () => {
	it("finds the busiest day, first peak wins ties", () => {
		const peak = peakDay(activityFromServer(serverResponse(), 3));
		expect(peak?.date).toBe("2026-09-02");
		expect(peak?.total).toBe(2);
		expect(peakDay(bucketActivity([], NOW))).toBe(null);
	});

	it("totals categories in server order", () => {
		const rows = categoryTotals(activityFromServer(serverResponse()));
		expect(rows).toEqual([
			{ category: "pricing", count: 3 },
			{ category: "content", count: 2 },
			{ category: "uncategorized", count: 2 },
		]);
	});
});

describe("fallbackView", () => {
	it("adapts monitors to the card view model", () => {
		const v = fallbackView([{ latest_change: { created_at: ago(1) } }], NOW, 7);
		expect(v.windowDays).toBe(7);
		expect(v.total).toBe(1);
		expect(v.fromServer).toBe(false);
	});
});
