import { describe, expect, it } from "vitest";
import { bucketActivity } from "@/lib/activity";

const NOW = new Date("2026-09-03T12:00:00Z");

function ago(hours: number): string {
	return new Date(NOW.getTime() - hours * 3_600_000).toISOString();
}

describe("bucketActivity", () => {
	it("returns 14 empty buckets when nothing changed", () => {
		const a = bucketActivity([], NOW);
		expect(a.counts).toHaveLength(14);
		expect(a.labels).toHaveLength(14);
		expect(a.total).toBe(0);
		expect(a.counts.every((c) => c === 0)).toBe(true);
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
		expect(a.counts[13]).toBe(2); // today
		expect(a.counts[12]).toBe(1); // yesterday
		expect(a.total).toBe(3);
	});

	it("ignores missing timestamps and future/out-of-range dates", () => {
		const a = bucketActivity(
			[
				{},
				{ latest_change: null },
				{ latest_change: { created_at: ago(24 * 20) } }, // 20 days ago
			],
			NOW,
		);
		expect(a.total).toBe(0);
	});

	it("labels run oldest-first ending today", () => {
		const a = bucketActivity([], NOW);
		const fmt = (d: Date) =>
			d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
		expect(a.labels[13]).toBe(fmt(NOW));
		const oldest = new Date(NOW);
		oldest.setDate(NOW.getDate() - 13);
		expect(a.labels[0]).toBe(fmt(oldest));
	});
});
