import type { ChangeActivity } from "@/lib/types";

export type ChangeTimestamp = {
	latest_change?: { created_at: string } | null;
};

/** One rendered day: total + per-category segments (empty when fallen back). */
export type ActivityDay = {
	date: string; // YYYY-MM-DD (UTC)
	label: string; // "Sep 3"
	total: number;
	byCategory: Record<string, number>;
};

/** View model for the dashboard activity card (server or client fallback). */
export type ActivityView = {
	days: ActivityDay[];
	categories: string[];
	total: number;
	windowDays: number;
	fromServer: boolean;
};

function utcDayString(d: Date): string {
	return d.toISOString().slice(0, 10);
}

export function formatDayLabel(yyyyMmDd: string): string {
	// Parse as UTC noon to avoid TZ-shift when formatting.
	const d = new Date(`${yyyyMmDd}T12:00:00Z`);
	if (Number.isNaN(d.getTime())) return yyyyMmDd;
	return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * Client-side fallback: bucket latest-change timestamps into per-day totals for
 * the trailing `days` UTC days (oldest first). Caps at 1 per monitor — the
 * server endpoint counts every event, so this only runs when it is unreachable.
 */
export function bucketActivity<T extends ChangeTimestamp>(
	items: T[],
	now: Date,
	days = 14,
): ActivityView {
	const todayUtc = new Date(
		Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
	);
	const dayKeys: string[] = [];
	for (let i = days - 1; i >= 0; i--) {
		dayKeys.push(utcDayString(new Date(todayUtc.getTime() - i * 86_400_000)));
	}
	const indexByDay = new Map(dayKeys.map((k, i) => [k, i]));
	const totals = Array<number>(days).fill(0);
	for (const item of items) {
		const ts = item.latest_change?.created_at;
		if (!ts) continue;
		const t = new Date(ts);
		if (Number.isNaN(t.getTime())) continue;
		if (t.getTime() > now.getTime()) continue; // future → ignore
		const idx = indexByDay.get(utcDayString(t));
		if (idx !== undefined) totals[idx] += 1;
	}
	return {
		days: dayKeys.map((date, i) => ({
			date,
			label: formatDayLabel(date),
			total: totals[i],
			byCategory: {},
		})),
		categories: [],
		total: totals.reduce((a, b) => a + b, 0),
		windowDays: days,
		fromServer: false,
	};
}

/**
 * Convert a server ChangeActivity response into the card view model,
 * slicing the trailing `windowDays` days (the response may carry a wider
 * range so the caller can compare against the previous window).
 */
export function activityFromServer(res: ChangeActivity, windowDays?: number): ActivityView {
	const n = windowDays ?? res.days;
	const buckets = res.buckets.slice(-n);
	return {
		days: buckets.map((b) => ({
			date: b.date,
			label: formatDayLabel(b.date),
			total: b.count,
			byCategory: b.by_category ?? {},
		})),
		categories: res.categories ?? [],
		total: buckets.reduce((a, b) => a + b.count, 0),
		windowDays: n,
		fromServer: true,
	};
}

/** Total of the window immediately before the trailing `windowDays` in a 2N response. */
export function previousWindowTotal(res: ChangeActivity, windowDays: number): number | null {
	if (res.days < windowDays * 2) return null;
	return res.counts.slice(0, windowDays).reduce((a, b) => a + b, 0);
}

/** Percent change of current vs previous total. Null when previous is 0/unknown. */
export function trendPct(current: number, previous: number | null): number | null {
	if (previous === null || previous <= 0) return null;
	return Math.round((100 * (current - previous)) / previous);
}

/** Busiest day in the view (first peak wins ties). Null when everything is 0. */
export function peakDay(view: ActivityView): ActivityDay | null {
	let best: ActivityDay | null = null;
	for (const d of view.days) {
		if (!best || d.total > best.total) best = d;
	}
	return best && best.total > 0 ? best : null;
}

/** Per-category totals across the view, ordered like `categories` (server) or by count. */
export function categoryTotals(view: ActivityView): Array<{ category: string; count: number }> {
	const totals = new Map<string, number>();
	for (const d of view.days) {
		for (const [cat, count] of Object.entries(d.byCategory)) {
			totals.set(cat, (totals.get(cat) ?? 0) + count);
		}
	}
	const rows = [...totals.entries()].map(([category, count]) => ({ category, count }));
	if (view.categories.length > 0) {
		const order = new Map(view.categories.map((c, i) => [c, i]));
		rows.sort((a, b) => (order.get(a.category) ?? 999) - (order.get(b.category) ?? 999));
	} else {
		rows.sort((a, b) => b.count - a.count);
	}
	return rows;
}

/** Client-fallback adapter: keep the overview card working with monitors only. */
export function fallbackView(
	items: ChangeTimestamp[],
	now: Date,
	windowDays: number,
): ActivityView {
	return bucketActivity(items, now, windowDays);
}
