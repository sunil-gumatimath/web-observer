"use client";

import { useMemo, useState } from "react";
import { cn, SegmentedControl } from "@/components/ui";
import { resolveImageUrl, splitLineSegments } from "@/lib/image-md";

/**
 * GitHub-style before/after diff.
 *
 * Line-level LCS over the two texts, rendered the way webdog/ GitHub show a
 * change: a split (side-by-side) view with removed lines in red on the
 * "Before" side and added lines in green on the "After" side, plus a unified
 * view. Falls back to the raw unified diff when the text is too large to diff
 * in the browser.
 */

type Row = {
	kind: "equal" | "del" | "add" | "replace";
	left?: string;
	leftNo?: number;
	right?: string;
	rightNo?: number;
};

const MAX_LINES = 1500;

function lineLcs(a: string[], b: string[]) {
	const n = a.length;
	const m = b.length;
	const dp: Uint32Array[] = [];
	for (let i = 0; i <= n; i++) dp.push(new Uint32Array(m + 1));
	for (let i = n - 1; i >= 0; i--) {
		for (let j = m - 1; j >= 0; j--) {
			dp[i][j] =
				a[i] === b[j]
					? dp[i + 1][j + 1] + 1
					: Math.max(dp[i + 1][j], dp[i][j + 1]);
		}
	}
	const ops: Array<{ t: "eq" | "del" | "add"; i: number; j: number }> = [];
	let i = 0;
	let j = 0;
	while (i < n && j < m) {
		if (a[i] === b[j]) {
			ops.push({ t: "eq", i, j });
			i++;
			j++;
		} else if (dp[i + 1][j] >= dp[i][j + 1]) {
			ops.push({ t: "del", i, j });
			i++;
		} else {
			ops.push({ t: "add", i, j });
			j++;
		}
	}
	while (i < n) {
		ops.push({ t: "del", i, j });
		i++;
	}
	while (j < m) {
		ops.push({ t: "add", i, j });
		j++;
	}
	return ops;
}

function buildRows(before: string, after: string): Row[] {
	const a = before.split("\n");
	const b = after.split("\n");
	const ops = lineLcs(a, b);
	const rows: Row[] = [];
	let k = 0;
	while (k < ops.length) {
		const op = ops[k];
		if (op.t === "eq") {
			rows.push({
				kind: "equal",
				left: a[op.i],
				leftNo: op.i + 1,
				right: b[op.j],
				rightNo: op.j + 1,
			});
			k++;
			continue;
		}
		const dels: number[] = [];
		const adds: number[] = [];
		while (k < ops.length && ops[k].t !== "eq") {
			if (ops[k].t === "del") dels.push(ops[k].i);
			else adds.push(ops[k].j);
			k++;
		}
		const max = Math.max(dels.length, adds.length);
		for (let x = 0; x < max; x++) {
			const hasDel = x < dels.length;
			const hasAdd = x < adds.length;
			if (hasDel && hasAdd) {
				rows.push({
					kind: "replace",
					left: a[dels[x]],
					leftNo: dels[x] + 1,
					right: b[adds[x]],
					rightNo: adds[x] + 1,
				});
			} else if (hasDel) {
				rows.push({ kind: "del", left: a[dels[x]], leftNo: dels[x] + 1 });
			} else {
				rows.push({ kind: "add", right: b[adds[x]], rightNo: adds[x] + 1 });
			}
		}
	}
	return rows;
}

function Gutter({ no }: { no?: number }) {
	return (
		<span className="w-10 shrink-0 select-none border-r border-[var(--border)] px-2 text-right text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
			{no ?? ""}
		</span>
	);
}

/**
 * Render a diff line, showing markdown images as small inline chips so
 * captured visuals (logos, screenshots of sections) are visible in alerts.
 * Unresolvable image tokens degrade to their alt text.
 */
function DiffLineText({ text, baseUrl }: { text: string; baseUrl?: string }) {
	const segs = useMemo(() => splitLineSegments(text || ""), [text]);
	if (segs.length === 0) return null;
	return (
		<>
			{segs.map((s, i) =>
				s.type === "image" ? (
					(() => {
						const url = resolveImageUrl(s.src, baseUrl);
						return url ? (
							// eslint-disable-next-line @next/next/no-img-element
							<img
								key={i}
								src={url}
								alt={s.alt}
								title={s.alt}
								loading="lazy"
								referrerPolicy="no-referrer"
								className="mx-0.5 inline-block max-h-8 max-w-[16rem] rounded border border-[var(--border)] align-middle"
							/>
						) : (
							<span key={i} className="italic opacity-70">
								[{s.alt || "image"}]
							</span>
						);
					})()
				) : (
					<span key={i}>{s.value}</span>
				),
			)}
		</>
	);
}

function SplitCell({
	text,
	no,
	variant,
	baseUrl,
}: {
	text?: string;
	no?: number;
	variant: "equal" | "del" | "add" | "empty";
	baseUrl?: string;
}) {
	const bg =
		variant === "del"
			? "bg-rose-500/10"
			: variant === "add"
				? "bg-emerald-500/10"
				: variant === "equal"
					? ""
					: "bg-slate-500/[0.02]";
	const txt =
		variant === "del"
			? "text-rose-700 dark:text-rose-300"
			: variant === "add"
				? "text-emerald-700 dark:text-emerald-300"
				: "text-slate-700 dark:text-slate-300";
	const sign = variant === "del" ? "−" : variant === "add" ? "+" : "";
	return (
		<div className={cn("flex min-h-[1.375rem] min-w-0 overflow-hidden", bg)}>
			<Gutter no={no} />
			<span
				className={cn(
					"min-w-0 flex-1 overflow-hidden whitespace-pre-wrap break-words px-2 [overflow-wrap:anywhere] [word-break:break-word]",
					txt,
				)}
			>
				{sign}
				<DiffLineText text={text ?? ""} baseUrl={baseUrl} />
			</span>
		</div>
	);
}

function UnifiedLine({
	text,
	variant,
	baseUrl,
}: {
	text: string;
	variant: "equal" | "del" | "add";
	baseUrl?: string;
}) {
	const cls =
		variant === "del"
			? "bg-rose-500/10 text-rose-700 dark:text-rose-300"
			: variant === "add"
				? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
				: "text-slate-600 dark:text-slate-300";
	const sign = variant === "del" ? "−" : variant === "add" ? "+" : " ";
	const srPrefix =
		variant === "del" ? "Removed: " : variant === "add" ? "Added: " : "";
	return (
		<div className={cn("flex min-w-0 overflow-hidden px-3", cls)}>
			<span className="min-w-0 flex-1 overflow-hidden whitespace-pre-wrap break-words [overflow-wrap:anywhere] [word-break:break-word]">
				{srPrefix ? <span className="sr-only">{srPrefix}</span> : null}
				<span aria-hidden="true">{sign}</span>
				<DiffLineText text={text} baseUrl={baseUrl} />
			</span>
		</div>
	);
}

/** Screen-reader-friendly linear rendering of the diff rows. */
function SrOnlyDiffSummary({ rows }: { rows: Row[] }) {
	const lines: string[] = [];
	for (const r of rows) {
		if (r.kind === "del") lines.push(`Removed: ${r.left ?? ""}`);
		else if (r.kind === "add") lines.push(`Added: ${r.right ?? ""}`);
		else if (r.kind === "replace") {
			lines.push(`Removed: ${r.left ?? ""}`);
			lines.push(`Added: ${r.right ?? ""}`);
		}
	}
	return <pre className="sr-only">{lines.join("\n")}</pre>;
}

export function GithubDiff({
	before,
	after,
	unifiedDiff,
	baseUrl,
}: {
	before: string | null;
	after: string | null;
	unifiedDiff?: string | null;
	baseUrl?: string;
}) {
	const [view, setView] = useState<"split" | "unified">("split");

	const tooLarge =
		(before?.split("\n").length ?? 0) > MAX_LINES ||
		(after?.split("\n").length ?? 0) > MAX_LINES;

	const rows = useMemo(
		() => (tooLarge ? [] : buildRows(before || "", after || "")),
		[before, after, tooLarge],
	);

	const hasContent = Boolean(before || after);
	if (!hasContent) {
		return (
			<p className="text-sm text-slate-500 dark:text-slate-400">
				No text content.
			</p>
		);
	}

	const added = rows.filter(
		(r) => r.kind === "add" || r.kind === "replace",
	).length;
	const removed = rows.filter(
		(r) => r.kind === "del" || r.kind === "replace",
	).length;

	const host = (() => {
		try {
			return baseUrl ? new URL(baseUrl).host : null;
		} catch {
			return null;
		}
	})();

	const header = (
		<div className="mb-3 flex flex-wrap items-center justify-between gap-3">
			<div className="flex flex-wrap items-center gap-2 text-sm">
				{host ? (
					<a
						href={baseUrl}
						target="_blank"
						rel="noreferrer"
						className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-neutral-50 px-2.5 py-1.5 text-xs text-neutral-600 ring-1 ring-neutral-950/5 transition hover:text-sky-700 hover:ring-sky-500/30 dark:bg-slate-900 dark:text-slate-400 dark:ring-white/10"
					>
						<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden className="size-3.5 shrink-0 text-neutral-400">
							<path d="M6.5 9.5a2.5 2.5 0 0 0 3.54 0l2-2a2.5 2.5 0 0 0-3.54-3.54l-.5.5" />
							<path d="M9.5 6.5a2.5 2.5 0 0 0-3.54 0l-2 2a2.5 2.5 0 0 0 3.54 3.54l.5-.5" />
						</svg>
						<span className="truncate font-mono">{host}</span>
					</a>
				) : (
					<span className="text-slate-600 dark:text-slate-300">Before → After</span>
				)}
			</div>
			<div className="flex items-center gap-1 rounded-lg bg-slate-100 p-0.5 dark:bg-slate-800/70">
				<SegmentedControl
					ariaLabel="Diff view"
					value={view}
					onChange={setView}
					options={[
						{ value: "split", label: "Split" },
						{ value: "unified", label: "Unified" },
					]}
				/>
			</div>
		</div>
	);

	const webdogHeader = (
		<div className="flex items-center justify-between gap-3 border-b border-neutral-950/5 bg-neutral-50/80 px-3 py-2 dark:border-white/5 dark:bg-slate-900/50">
			<p className="text-xs font-semibold text-neutral-700 dark:text-slate-300">What changed</p>
			{!tooLarge ? (
				<div className="flex items-center gap-1.5 tabular-nums">
					<span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-50 px-2 py-0.5 text-[0.6875rem] font-semibold text-emerald-700 ring-1 ring-emerald-600/15 ring-inset dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-500/20">
						<span aria-hidden>＋</span>{added} added
					</span>
					<span className="inline-flex items-center gap-0.5 rounded-full bg-rose-50 px-2 py-0.5 text-[0.6875rem] font-semibold text-rose-700 ring-1 ring-rose-600/15 ring-inset dark:bg-rose-950/30 dark:text-rose-300 dark:ring-rose-500/20">
						<span aria-hidden>－</span>{removed} removed
					</span>
				</div>
			) : null}
		</div>
	);

	if (tooLarge) {
		return (
			<div className="min-w-0 w-full max-w-full overflow-hidden">
				{header}
				<CardShell>
					<pre className="diff m-0 w-full min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-[13px] leading-5 [overflow-wrap:anywhere]">
						{unifiedDiff ? (
							unifiedDiff.split("\n").map((line, i) => {
								const t = line.trimStart();
								if (t.startsWith("+") && !t.startsWith("+++"))
									return (
										<span key={i} className="add block">
											{line}
										</span>
									);
								if (t.startsWith("-") && !t.startsWith("---"))
									return (
										<span key={i} className="del block">
											{line}
										</span>
									);
								return (
									<span key={i} className="block">
										{line}
									</span>
								);
							})
						) : (
							<span className="text-slate-500">No diff available.</span>
						)}
					</pre>
				</CardShell>
			</div>
		);
	}

	if (view === "unified") {
		return (
			<div className="min-w-0 w-full max-w-full overflow-hidden">
				{header}
				<div className="overflow-hidden rounded-xl ring-1 ring-neutral-950/[0.08] shadow-xs dark:ring-white/10">
					{webdogHeader}
					<div className="max-h-72 overflow-auto bg-white dark:bg-slate-950">
						<table className="w-full border-collapse font-mono text-xs">
							<tbody>
								{rows.map((r, i) => {
									if (r.kind === "equal") return null;
									if (r.kind === "del")
										return (
											<tr key={i} className="bg-rose-50/60 dark:bg-rose-950/20">
												<td aria-hidden className="w-6 border-r border-neutral-950/5 bg-rose-100/80 px-2 text-center font-semibold select-none text-rose-700 dark:border-white/5 dark:bg-rose-900/30 dark:text-rose-300">−</td>
												<td className="px-3 py-1 break-all whitespace-pre-wrap text-rose-900 dark:text-rose-200"><mark className="rounded-sm bg-rose-200/80 px-0.5 text-rose-950 dark:bg-rose-900/40 dark:text-rose-100 [box-decoration-break:clone]"><DiffLineText text={r.left ?? ""} baseUrl={baseUrl} /></mark></td>
											</tr>
										);
									if (r.kind === "add")
										return (
											<tr key={i} className="bg-emerald-50/60 dark:bg-emerald-950/20">
												<td aria-hidden className="w-6 border-r border-neutral-950/5 bg-emerald-100/80 px-2 text-center font-semibold select-none text-emerald-700 dark:border-white/5 dark:bg-emerald-900/30 dark:text-emerald-300">+</td>
												<td className="px-3 py-1 break-all whitespace-pre-wrap text-emerald-900 dark:text-emerald-200"><mark className="rounded-sm bg-emerald-200/80 px-0.5 text-emerald-950 dark:bg-emerald-900/40 dark:text-emerald-100 [box-decoration-break:clone]"><DiffLineText text={r.right ?? ""} baseUrl={baseUrl} /></mark></td>
											</tr>
										);
									return (
										<>
											<tr key={`${i}-del`} className="bg-rose-50/60 dark:bg-rose-950/20">
												<td aria-hidden className="w-6 border-r border-neutral-950/5 bg-rose-100/80 px-2 text-center font-semibold select-none text-rose-700 dark:border-white/5 dark:bg-rose-900/30 dark:text-rose-300">−</td>
												<td className="px-3 py-1 break-all whitespace-pre-wrap text-rose-900 dark:text-rose-200"><mark className="rounded-sm bg-rose-200/80 px-0.5 text-rose-950 dark:bg-rose-900/40 dark:text-rose-100 [box-decoration-break:clone]"><DiffLineText text={r.left ?? ""} baseUrl={baseUrl} /></mark></td>
											</tr>
											<tr key={`${i}-add`} className="bg-emerald-50/60 dark:bg-emerald-950/20">
												<td aria-hidden className="w-6 border-r border-neutral-950/5 bg-emerald-100/80 px-2 text-center font-semibold select-none text-emerald-700 dark:border-white/5 dark:bg-emerald-900/30 dark:text-emerald-300">+</td>
												<td className="px-3 py-1 break-all whitespace-pre-wrap text-emerald-900 dark:text-emerald-200"><mark className="rounded-sm bg-emerald-200/80 px-0.5 text-emerald-950 dark:bg-emerald-900/40 dark:text-emerald-100 [box-decoration-break:clone]"><DiffLineText text={r.right ?? ""} baseUrl={baseUrl} /></mark></td>
											</tr>
										</>
									);
								})}
							</tbody>
						</table>
					</div>
				</div>
			</div>
		);
	}

	return (
		<div className="min-w-0 w-full max-w-full overflow-hidden">
			{header}
			{/* Screen-reader alternative: linear added/removed summary of the split view. */}
			<SrOnlyDiffSummary rows={rows} />
			<div aria-hidden="true" className="min-w-0 w-full max-w-full overflow-hidden">
				<CardShell>
					<div className="grid w-full min-w-0 grid-cols-2 border-b border-[var(--border)] bg-slate-50/70 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:bg-slate-900/50 dark:text-slate-400">
						<div className="min-w-0 overflow-hidden px-2 py-1.5">Before</div>
						<div className="min-w-0 overflow-hidden px-2 py-1.5">After</div>
					</div>
					<div className="max-h-[min(70vh,32rem)] w-full min-w-0 max-w-full overflow-auto">
						{rows.map((r, i) => (
							<div key={i} className="grid w-full min-w-0 grid-cols-2">
								{r.kind === "del" ? (
									<>
										<SplitCell text={r.left} no={r.leftNo} variant="del" baseUrl={baseUrl} />
										<SplitCell variant="empty" baseUrl={baseUrl} />
									</>
								) : r.kind === "add" ? (
									<>
										<SplitCell variant="empty" baseUrl={baseUrl} />
										<SplitCell text={r.right} no={r.rightNo} variant="add" baseUrl={baseUrl} />
									</>
								) : r.kind === "replace" ? (
									<>
										<SplitCell text={r.left} no={r.leftNo} variant="del" baseUrl={baseUrl} />
										<SplitCell text={r.right} no={r.rightNo} variant="add" baseUrl={baseUrl} />
									</>
								) : (
									<>
										<SplitCell text={r.left} no={r.leftNo} variant="equal" baseUrl={baseUrl} />
										<SplitCell text={r.right} no={r.rightNo} variant="equal" baseUrl={baseUrl} />
									</>
								)}
							</div>
						))}
					</div>
				</CardShell>
			</div>
		</div>
	);
}

function CardShell({ children }: { children: React.ReactNode }) {
	return (
		<div className="w-full min-w-0 max-w-full overflow-hidden rounded-xl border border-[var(--border)] bg-white shadow-sm dark:bg-slate-950/40">
			{children}
		</div>
	);
}
