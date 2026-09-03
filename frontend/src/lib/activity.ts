export type ChangeTimestamp = {
	latest_change?: { created_at: string } | null;
};

export type Activity = {
	counts: number[];
	labels: string[];
	total: number;
};

/**
 * Bucket latest-change timestamps into per-day counts for the trailing
 * `days` days (oldest first). Pure — pass `now` explicitly for tests.
 */
export function bucketActivity<T extends ChangeTimestamp>(
	items: T[],
	now: Date,
	days = 14,
): Activity {
	const counts = Array<number>(days).fill(0);
	const labels: string[] = [];
	for (let i = days - 1; i >= 0; i--) {
		const d = new Date(now);
		d.setDate(now.getDate() - i);
		labels.push(
			d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
		);
	}
	for (const item of items) {
		const ts = item.latest_change?.created_at;
		if (!ts) continue;
		const diffDays = Math.floor(
			(now.getTime() - new Date(ts).getTime()) / 86_400_000,
		);
		if (diffDays >= 0 && diffDays < days) counts[days - 1 - diffDays] += 1;
	}
	return { counts, labels, total: counts.reduce((a, b) => a + b, 0) };
}
