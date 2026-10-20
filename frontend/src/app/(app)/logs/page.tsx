"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
	Badge,
	Button,
	EmptyState,
	ErrorBox,
	Input,
	PageHeader,
	Select,
	Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { Monitor, MonitorRunLog } from "@/lib/types";
import { usePageTitle } from "@/lib/use-page-title";
import { useAutoRefresh } from "@/lib/use-auto-refresh";
import { ensureWorkspace } from "@/lib/workspace";

type Outcome = "all" | "success" | "failed" | "changed";

const PAGE_SIZE = 50;

/** Per-run status badge, mirroring the monitor detail run-history table. */
function statusTone(status: string): "neutral" | "success" | "danger" | "info" {
	if (status === "succeeded") return "success";
	if (status === "failed") return "danger";
	if (status === "running") return "info";
	return "neutral";
}

export default function LogsPage() {
	usePageTitle("Logs");
	const [workspaceId, setWorkspaceId] = useState<string | null>(null);
	const [monitors, setMonitors] = useState<Monitor[]>([]);
	const [rows, setRows] = useState<MonitorRunLog[]>([]);
	const [total, setTotal] = useState(0);
	const [outcome, setOutcome] = useState<Outcome>("all");
	const [monitorFilter, setMonitorFilter] = useState<string>("all");
	const [dateFrom, setDateFrom] = useState("");
	const [dateTo, setDateTo] = useState("");
	const [limit, setLimit] = useState(PAGE_SIZE);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [refreshTick, setRefreshTick] = useState(0);

	const load = useCallback(
		async (ws: string, lim: number) => {
			const page = await api.listRunLogs(ws, {
				...(monitorFilter !== "all" ? { monitorId: monitorFilter } : {}),
				...(outcome !== "all" ? { outcome } : {}),
				...(dateFrom ? { from: dateFrom } : {}),
				...(dateTo ? { to: dateTo } : {}),
				limit: lim,
			});
			setRows(page.items);
			setTotal(page.total);
		},
		[monitorFilter, outcome, dateFrom, dateTo],
	);

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const ws = await ensureWorkspace();
				if (cancelled) return;
				setWorkspaceId(ws);
				await load(ws, limit);
			} catch (e) {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load run logs");
			} finally {
				if (!cancelled) setLoading(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [limit, load, refreshTick]);

	// Load the monitor dropdown once per workspace. Done separately from the
	// run-log fetch so the filter options never jitter as runs refresh.
	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const ws = await ensureWorkspace();
				const list = await api.listMonitors(ws);
				if (!cancelled) setMonitors(list);
			} catch {
				// Non-fatal: the dropdown stays empty, list still shows monitor names.
			}
		})();
		return () => {
			cancelled = true;
		};
	}, []);

	// 15s cadence so runs started elsewhere (scheduler, another tab, Run now
	// on a monitor) surface without a manual refresh.
	useAutoRefresh(() => setRefreshTick((n) => n + 1));

	function resetFilters() {
		setMonitorFilter("all");
		setOutcome("all");
		setDateFrom("");
		setDateTo("");
		setLimit(PAGE_SIZE);
	}

	const hasFilters =
		monitorFilter !== "all" || outcome !== "all" || Boolean(dateFrom || dateTo);
	const serverFilters = {
		...(monitorFilter !== "all" ? { monitorId: monitorFilter } : {}),
		...(outcome !== "all" ? { outcome } : {}),
		...(dateFrom ? { from: dateFrom } : {}),
		...(dateTo ? { to: dateTo } : {}),
	};

	if (loading) return <Spinner />;

	return (
		<div>
			<PageHeader
				title="Logs"
				description="Every check run across the workspace — successes, failures and detections. Same filters drive the CSV export."
				actions={
					<div className="flex items-center gap-2">
						<Button
							type="button"
							variant="secondary"
							disabled={!workspaceId}
							onClick={() => {
								if (!workspaceId) return;
								window.open(
									api.exportRunLogsUrl(workspaceId, serverFilters),
									"_blank",
								);
							}}
						>
							Export CSV
						</Button>
					</div>
				}
			/>
			{error ? <ErrorBox message={error} /> : null}

			{/* Outcome tabs + filters */}
			<div className="mb-6">
				<OutcomeTabs
					value={outcome}
					total={total}
					onChange={(key) => {
						setOutcome(key);
						setLimit(PAGE_SIZE);
					}}
				/>
			</div>

			<div className="mb-6 flex flex-wrap items-center gap-2">
				<div className="w-full sm:w-60 sm:shrink-0">
					<Select
						value={monitorFilter}
						onChange={(e) => {
							setMonitorFilter(e.target.value);
							setLimit(PAGE_SIZE);
						}}
						aria-label="Filter by monitor"
						className="h-9 w-full"
					>
						<option value="all">All monitors</option>
						{monitors.map((m) => (
							<option key={m.id} value={m.id}>
								{m.name}
							</option>
						))}
					</Select>
				</div>
				<Input
					type="date"
					value={dateFrom}
					onChange={(e) => {
						setDateFrom(e.target.value);
						setLimit(PAGE_SIZE);
					}}
					aria-label="From date"
					className="h-9 w-auto"
				/>
				<Input
					type="date"
					value={dateTo}
					onChange={(e) => {
						setDateTo(e.target.value);
						setLimit(PAGE_SIZE);
					}}
					aria-label="To date"
					className="h-9 w-auto"
				/>
				{hasFilters ? (
					<Button type="button" variant="ghost" size="sm" onClick={resetFilters}>
						Clear
					</Button>
				) : null}
			</div>

			{/* Run table */}
			{rows.length === 0 ? (
				hasFilters ? (
					<EmptyState
						title="No matching runs"
						body="No runs match your current filters. Try clearing them."
						action={
							<Button type="button" variant="secondary" onClick={resetFilters}>
								Clear filters
							</Button>
						}
					/>
				) : (
					<EmptyState
						title="No runs yet"
						body="Runs appear here the moment a check is queued — manual or scheduled."
						action={
							<Link href="/monitors/new">
								<Button type="button">Create a monitor</Button>
							</Link>
						}
					/>
				)
			) : (
				<div className="surface mb-4 overflow-hidden">
					<div className="overflow-x-auto">
						<table className="w-full text-left text-sm">
							<thead>
								<tr className="border-b border-[var(--hairline)] bg-[var(--surface-1)]">
									{["Monitor", "Status", "Changed", "HTTP", "Latency", "Error", "Finished"].map(
										(h) => (
											<th
												key={h}
												className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-subtle)]"
											>
												{h}
											</th>
										),
									)}
								</tr>
							</thead>
							<tbody className="divide-y divide-[var(--border)]">
								{rows.map((r) => (
									<tr
										key={r.id}
										className="transition hover:bg-[var(--surface-2)]"
									>
										<td className="max-w-xs px-4 py-3">
											<Link
												href={`/logs/${r.id}`}
												className="block truncate font-medium text-[var(--fg)] hover:text-[var(--primary)]"
												title="Open run detail"
											>
												{r.monitor_name}
											</Link>
										</td>
										<td className="px-4 py-3">
											<Badge tone={statusTone(r.status)}>{r.status}</Badge>
										</td>
										<td className="px-4 py-3">
											{r.changed && r.change_id ? (
												<Link href={`/changes/${r.change_id}`}>
													<Badge tone="warn">view diff</Badge>
												</Link>
											) : r.status === "succeeded" ? (
												<span
													className="text-[var(--ink-tertiary)]"
													title="Baseline or unchanged content"
												>
													—
												</span>
											) : (
												<span className="text-[var(--ink-tertiary)]">—</span>
											)}
										</td>
										<td className="px-4 py-3 text-[var(--ink-muted)]">
											{r.http_status ?? "—"}
										</td>
										<td className="px-4 py-3 text-[var(--ink-muted)]">
											{r.latency_ms != null ? `${r.latency_ms}ms` : "—"}
										</td>
										<td
											className="max-w-[14rem] truncate px-4 py-3 text-[var(--ink-muted)]"
											title={
												r.error_message
													? `${r.error_code ?? "error"} — ${r.error_message}`
													: undefined
											}
										>
											{r.error_code ?? "—"}
										</td>
										<td className="px-4 py-3 text-[var(--ink-subtle)]">
											<span
												title={new Date(
													r.finished_at ?? r.scheduled_at,
												).toLocaleString()}
											>
												{relativeTime(r.finished_at ?? r.scheduled_at)}
											</span>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				</div>
			)}

			{/* Pagination / Load more */}
			{rows.length < total ? (
				<p className="mb-4 text-center text-xs text-[var(--ink-subtle)]">
					Showing {rows.length} of {total} runs for this filter.
				</p>
			) : null}
			{rows.length >= limit && rows.length < total ? (
				<div className="flex justify-center">
					<Button
						type="button"
						variant="secondary"
						onClick={() => setLimit((l) => l + PAGE_SIZE)}
					>
						Load more
					</Button>
				</div>
			) : null}
		</div>
	);
}

function OutcomeTabs({
	value,
	total,
	onChange,
}: {
	value: Outcome;
	total: number;
	onChange: (key: Outcome) => void;
}) {
	const labels: Record<Outcome, string> = {
		all: "All" + (total > 0 ? ` · ${total}` : ""),
		success: "Success",
		failed: "Failed",
		changed: "Changed",
	};
	return (
		<div className="flex flex-wrap gap-2" role="tablist" aria-label="Run outcome filter">
			{(Object.keys(labels) as Outcome[]).map((key) => (
				<button
					key={key}
					type="button"
					role="tab"
					aria-selected={value === key}
					onClick={() => onChange(key)}
					className={`rounded-[8px] border px-3 py-1.5 text-sm font-medium transition ${
						value === key
							? "border-transparent bg-[var(--primary)] text-white"
							: "border-[var(--hairline)] bg-[var(--surface-1)] text-[var(--muted)] hover:border-[var(--hairline-strong)] hover:text-[var(--fg)]"
					}`}
				>
					{labels[key]}
				</button>
			))}
		</div>
	);
}
