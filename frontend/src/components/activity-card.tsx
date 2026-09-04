"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { api } from "@/lib/api";
import {
	activityFromServer,
	categoryTotals,
	fallbackView,
	peakDay,
	previousWindowTotal,
	trendPct,
} from "@/lib/activity";
import type { ChangeActivity, Monitor } from "@/lib/types";

const RANGES = [7, 14, 30] as const;
type Range = (typeof RANGES)[number];

const CATEGORY_STYLES: Record<string, string> = {
	pricing: "bg-emerald-500",
	availability: "bg-[var(--accent)]",
	legal: "bg-amber-500",
	content: "bg-violet-500",
	design: "bg-pink-500",
	api: "bg-indigo-500",
	security: "bg-rose-500",
	other: "bg-slate-400",
	uncategorized: "bg-slate-300 dark:bg-slate-600",
};

function categoryClass(cat: string): string {
	return CATEGORY_STYLES[cat] ?? "bg-slate-400";
}

function tooltipFor(dayLabel: string, total: number, byCategory: Record<string, number>): string {
	const head = `${dayLabel}: ${total} change${total === 1 ? "" : "s"}`;
	const cats = Object.keys(byCategory);
	if (cats.length === 0) return head;
	const detail = Object.entries(byCategory)
		.sort((a, b) => b[1] - a[1])
		.map(([cat, count]) => `${cat} ${count}`)
		.join(", ");
	return `${head} (${detail})`;
}

export function ActivityCard({
	workspaceId,
	monitors,
}: {
	workspaceId: string;
	monitors: Monitor[];
}) {
	const [range, setRange] = useState<Range>(14);
	const [resp, setResp] = useState<ChangeActivity | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		if (!workspaceId) return;
		let cancelled = false;
		// Fetch a double window so the card can trend against the prior period.
		api
			.getChangeActivity(workspaceId, { days: range * 2 })
			.then((r) => {
				if (!cancelled) setResp(r);
			})
			.catch(() => {
				if (!cancelled) setResp(null);
			})
			.finally(() => {
				if (!cancelled) setLoading(false);
			});
		return () => {
			cancelled = true;
		};
	}, [workspaceId, range]);

	const view = resp ? activityFromServer(resp, range) : fallbackView(monitors, new Date(), range);
	const prev = resp ? previousWindowTotal(resp, range) : null;
	const pct = trendPct(view.total, prev);
	const peak = peakDay(view);
	const cats = categoryTotals(view);
	const max = Math.max(1, ...view.days.map((d) => d.total));
	const avg = view.total / range;
	const first = view.days[0];
	const last = view.days[view.days.length - 1];

	return (
		<Card className="mb-8">
			<div className="flex flex-wrap items-start justify-between gap-4">
				<div>
					<p className="section-label">Change activity</p>
					<p className="mt-1 text-sm text-[var(--muted)]">
						{view.total === 0 ? (
							`No changes detected in the last ${range} days.`
						) : (
							<>
								<span className="text-lg font-semibold text-[var(--fg)]">{view.total}</span>{" "}
								change{view.total === 1 ? "" : "s"} in the last {range} days
								{pct !== null ? (
									<span
										className={`ml-2 text-xs font-medium ${pct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"}`}
									>
										{pct >= 0 ? "+" : ""}
										{pct}% vs prior {range}d
									</span>
								) : null}
							</>
						)}
					</p>
					{view.total > 0 ? (
						<p className="mt-0.5 text-xs text-[var(--muted)]">
							≈{avg < 10 && avg !== Math.round(avg) ? avg.toFixed(1) : Math.round(avg)}/day
							{peak ? ` · peak ${peak.label} (${peak.total})` : ""}
							{!view.fromServer ? " · live breakdown unavailable" : ""}
						</p>
					) : null}
				</div>
				<div
					className="flex items-center gap-1 rounded-lg border border-[var(--border)] p-1"
					role="group"
					aria-label="Activity range"
				>
					{RANGES.map((r) => (
						<button
							key={r}
							type="button"
							aria-pressed={range === r}
							onClick={() => {
								setRange(r);
								setLoading(true);
							}}
							className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
								range === r
									? "bg-[var(--accent)] text-white"
									: "text-[var(--muted)] hover:text-[var(--fg)]"
							}`}
						>
							{r}D
						</button>
					))}
				</div>
			</div>

			<div className="mt-4">
				<div
					className={`flex items-end gap-1 ${loading ? "opacity-60" : ""}`}
					role="img"
					aria-label={`Changes per day, last ${range} days`}
				>
					{view.days.map((d) => {
						const segs = Object.entries(d.byCategory).sort((a, b) => b[1] - a[1]);
						const isPeak = peak !== null && d.date === peak.date;
						return (
							<div
								key={d.date}
								title={tooltipFor(d.label, d.total, d.byCategory)}
								className={`flex-1 overflow-hidden rounded-sm transition-all ${
									isPeak ? "ring-1 ring-[var(--accent)] ring-offset-1 ring-offset-transparent" : ""
								}`}
								style={{ height: `${8 + (d.total / max) * 56}px`, minWidth: 3 }}
							>
								{d.total === 0 ? (
									<div className="h-full w-full bg-[var(--accent)] opacity-25" />
								) : segs.length > 0 ? (
									<div className="flex h-full w-full flex-col justify-end">
										{segs.map(([cat, count]) => (
											<div
												key={cat}
												className={`${categoryClass(cat)} w-full`}
												style={{ height: `${(count / d.total) * 100}%`, minHeight: count > 0 ? 2 : 0 }}
											/>
										))}
									</div>
								) : (
									<div className="h-full w-full bg-[var(--accent)]/70 hover:opacity-80" />
								)}
							</div>
						);
					})}
				</div>
				<div className="mt-1.5 flex items-center justify-between text-[10px] text-[var(--muted)]">
					<span>
						{first?.label} – {last?.label}
					</span>
					<Link href="/alerts" className="font-medium text-[var(--accent)] hover:opacity-80">
						View alerts →
					</Link>
				</div>
				{cats.length > 0 ? (
					<div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
						{cats.map(({ category, count }) => (
							<span
								key={category}
								className="inline-flex items-center gap-1.5 text-[11px] text-[var(--muted)]"
							>
								<span className={`h-2 w-2 rounded-full ${categoryClass(category)}`} aria-hidden />
								{category} · {count}
							</span>
						))}
					</div>
				) : null}
			</div>
		</Card>
	);
}
