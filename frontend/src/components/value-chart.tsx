"use client";

import { useMemo } from "react";
import type { ValuePoint } from "@/lib/types";

const W = 560;
const H = 160;
const PAD = 28;

/** Minimal dependency-free line chart for price / JSON value history. */
export function ValueChart({ points }: { points: ValuePoint[] }) {
	const geom = useMemo(() => {
		if (points.length < 2) return null;
		const vs = points.map((p) => p.value);
		let lo = Math.min(...vs);
		let hi = Math.max(...vs);
		if (lo === hi) {
			lo -= 1;
			hi += 1;
		}
		const span = hi - lo || 1;
		const x = (i: number) =>
			PAD + (i / (points.length - 1)) * (W - PAD * 2);
		const y = (v: number) => H - PAD - ((v - lo) / span) * (H - PAD * 2);
		const d = points
			.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`)
			.join(" ");
		const last = points[points.length - 1];
		const first = points[0];
		return { d, lo, hi, lx: x(points.length - 1), ly: y(last.value), last, first };
	}, [points]);

	if (points.length === 0) {
		return (
			<p className="text-sm text-slate-500 dark:text-slate-500">
				No numeric values recorded yet — history builds up as checks run.
			</p>
		);
	}
	if (!geom) {
		const only = points[0];
		return (
			<p className="text-sm text-slate-500 dark:text-slate-500">
				Current value: <strong className="text-[var(--fg)]">{only.value}</strong> — the
				trend appears after the next check.
			</p>
		);
	}
	const delta = geom.last.value - geom.first.value;
	const up = delta >= 0;
	return (
		<div>
			<div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
				<span className="text-2xl font-semibold tracking-tight text-[var(--fg)]">
					{geom.last.value}
				</span>
				<span
					className={`text-sm font-medium ${up ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}
				>
					{up ? "▲" : "▼"} {Math.abs(delta).toFixed(2)} since{" "}
					{new Date(geom.first.t).toLocaleDateString()}
				</span>
				<span className="text-xs text-slate-500 dark:text-slate-500">
					{points.length} points · low {geom.lo} · high {geom.hi}
				</span>
			</div>
			<svg
				viewBox={`0 0 ${W} ${H}`}
				className="w-full rounded-xl border border-[var(--border)] bg-slate-50/60 dark:bg-slate-950/40"
				role="img"
				aria-label={`Value trend: ${geom.first.value} to ${geom.last.value}`}
			>
				<path d={geom.d} fill="none" stroke="var(--accent)" strokeWidth="2" />
				<circle cx={geom.lx} cy={geom.ly} r="3.5" fill="var(--accent)" />
			</svg>
		</div>
	);
}
