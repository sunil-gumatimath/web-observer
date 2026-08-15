"use client";

import { useMemo, useState } from "react";
import { cn, SegmentedControl } from "@/components/ui";

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

function SplitCell({
	text,
	no,
	variant,
}: {
	text?: string;
	no?: number;
	variant: "equal" | "del" | "add" | "empty";
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
		<div className={cn("flex min-h-[1.375rem]", bg)}>
			<Gutter no={no} />
			<span className={cn("whitespace-pre-wrap break-words px-2", txt)}>
				{sign}
				{text ?? ""}
			</span>
		</div>
	);
}

function UnifiedLine({
	text,
	variant,
}: {
	text: string;
	variant: "equal" | "del" | "add";
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
		<div className={cn("flex px-3", cls)}>
			<span className="whitespace-pre-wrap break-words">
				{srPrefix ? <span className="sr-only">{srPrefix}</span> : null}
				<span aria-hidden="true">{sign}</span>
				{text}
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
}: {
	before: string | null;
	after: string | null;
	unifiedDiff?: string | null;
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

	const header = (
		<div className="mb-3 flex flex-wrap items-center justify-between gap-3">
			<div className="flex flex-wrap items-center gap-2 text-sm">
				<span className="text-slate-600 dark:text-slate-300">
					Before → After
				</span>
				{!tooLarge ? (
					<>
						<span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
							+{added}
						</span>
						<span className="rounded bg-rose-500/15 px-2 py-0.5 text-[11px] font-semibold text-rose-700 dark:text-rose-300">
							−{removed}
						</span>
					</>
				) : null}
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

	if (tooLarge) {
		return (
			<div>
				{header}
				<CardShell>
					<pre className="diff m-0 whitespace-pre-wrap break-words p-3 font-mono text-[13px] leading-5">
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
			<div>
				{header}
				<CardShell>
					<div className="max-h-[min(70vh,32rem)] overflow-auto py-1 font-mono text-[13px] leading-5">
						{rows.map((r, i) => {
							if (r.kind === "equal")
								return (
									<UnifiedLine key={i} text={r.left ?? ""} variant="equal" />
								);
							if (r.kind === "del")
								return (
									<UnifiedLine key={i} text={r.left ?? ""} variant="del" />
								);
							if (r.kind === "add")
								return (
									<UnifiedLine key={i} text={r.right ?? ""} variant="add" />
								);
							return (
								<div key={i}>
									<UnifiedLine text={r.left ?? ""} variant="del" />
									<UnifiedLine text={r.right ?? ""} variant="add" />
								</div>
							);
						})}
					</div>
				</CardShell>
			</div>
		);
	}

	return (
		<div>
			{header}
			{/* Screen-reader alternative: linear added/removed summary of the split view. */}
			<SrOnlyDiffSummary rows={rows} />
			<div aria-hidden="true">
				<CardShell>
					<div className="grid grid-cols-2 border-b border-[var(--border)] bg-slate-50/70 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:bg-slate-900/50 dark:text-slate-400">
						<div className="px-2 py-1.5">Before</div>
						<div className="px-2 py-1.5">After</div>
					</div>
					<div className="max-h-[min(70vh,32rem)] overflow-auto">
						{rows.map((r, i) => (
							<div key={i} className="grid grid-cols-2">
								{r.kind === "del" ? (
									<>
										<SplitCell text={r.left} no={r.leftNo} variant="del" />
										<SplitCell variant="empty" />
									</>
								) : r.kind === "add" ? (
									<>
										<SplitCell variant="empty" />
										<SplitCell text={r.right} no={r.rightNo} variant="add" />
									</>
								) : r.kind === "replace" ? (
									<>
										<SplitCell text={r.left} no={r.leftNo} variant="del" />
										<SplitCell text={r.right} no={r.rightNo} variant="add" />
									</>
								) : (
									<>
										<SplitCell text={r.left} no={r.leftNo} variant="equal" />
										<SplitCell text={r.right} no={r.rightNo} variant="equal" />
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
		<div className="overflow-hidden rounded-xl border border-[var(--border)] bg-white shadow-sm dark:bg-slate-950/40">
			{children}
		</div>
	);
}
