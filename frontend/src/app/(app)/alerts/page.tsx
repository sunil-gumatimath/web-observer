"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
	Badge,
	Button,
	Card,
	EmptyState,
	ErrorBox,
	Input,
	PageHeader,
	SegmentedControl,
	Select,
	Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { AlertInboxItem, AlertsSummary } from "@/lib/types";
import { usePageTitle } from "@/lib/use-page-title";
import { ensureWorkspace } from "@/lib/workspace";

type Filter = "all" | "unread" | "noise";

const PAGE_SIZE = 100;

const CHANGE_COLORS: Record<string, string> = {
	pricing: "bg-emerald-500",
	availability: "bg-sky-500",
	legal: "bg-amber-500",
	content: "bg-violet-500",
	design: "bg-pink-500",
	api: "bg-indigo-500",
	security: "bg-rose-500",
	other: "bg-slate-400",
};

const CATEGORY_LABEL: Record<string, string> = {
	pricing: "Pricing",
	availability: "Availability",
	legal: "Legal",
	content: "Content",
	design: "Design",
	api: "API",
	security: "Security",
	other: "Change",
};

function changeDotClass(cat: string | null): string {
	if (!cat) return "bg-slate-300 dark:bg-slate-600";
	return CHANGE_COLORS[cat] ?? "bg-slate-400";
}

function relativeTime(iso: string): string {
	const diff = Date.now() - new Date(iso).getTime();
	const m = Math.floor(diff / 60000);
	if (m < 1) return "just now";
	if (m < 60) return `${m}m ago`;
	const h = Math.floor(m / 60);
	if (h < 24) return `${h}h ago`;
	const d = Math.floor(h / 24);
	if (d < 30) return `${d}d ago`;
	return new Date(iso).toLocaleDateString();
}

/** Pull the AI triage reason out of a noise item's summary, if present. */
function triageReason(summary: string | null): string | null {
	if (!summary) return null;
	const m = summary.match(/^\[AI triage\]\s*(.+)$/i);
	return m ? m[1] : null;
}

export default function AlertsPage() {
	usePageTitle("Alerts");
	const router = useRouter();
	const [workspaceId, setWorkspaceId] = useState<string | null>(null);
	const [alerts, setAlerts] = useState<AlertInboxItem[]>([]);
	const [summary, setSummary] = useState<AlertsSummary | null>(null);
	const [filter, setFilter] = useState<Filter>("all");
	const [query, setQuery] = useState("");
	const [monitorFilter, setMonitorFilter] = useState<string>("all");
	const [dateFrom, setDateFrom] = useState("");
	const [dateTo, setDateTo] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);
	const [busy, setBusy] = useState(false);
	const [limit, setLimit] = useState(PAGE_SIZE);

	const load = useCallback(async (ws: string, f: Filter, lim: number) => {
		const [items, sum] = await Promise.all([
			api
				.listAlerts(ws, {
					unread_only: f === "unread",
					include_noise: f === "noise" || f === "all",
					limit: lim,
				})
				.then((list) =>
					f === "noise"
						? list.filter((a) => a.is_noise)
						: f === "all"
							? list.filter((a) => !a.is_noise)
							: list,
				),
			api.alertsSummary(ws),
		]);
		setAlerts(items);
		setSummary(sum);
	}, []);

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const ws = await ensureWorkspace();
				if (cancelled) return;
				setWorkspaceId(ws);
				await load(ws, filter, limit);
			} catch (e) {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load alerts");
			} finally {
				if (!cancelled) setLoading(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [filter, limit, load]);

	// Distinct monitors present in the inbox, for the monitor filter dropdown.
	const monitorOptions = useMemo(() => {
		const seen = new Map<string, string>();
		for (const a of alerts) seen.set(a.monitor_id, a.monitor_name);
		return [...seen.entries()].map(([id, name]) => ({ id, name }));
	}, [alerts]);

	// Client-side search + filters applied on top of the fetched inbox.
	const visibleAlerts = useMemo(() => {
		const q = query.trim().toLowerCase();
		const fromMs = dateFrom ? new Date(dateFrom).getTime() : null;
		const toMs = dateTo
			? new Date(dateTo).getTime() + 24 * 60 * 60 * 1000 - 1
			: null;
		return alerts.filter((a) => {
			if (monitorFilter !== "all" && a.monitor_id !== monitorFilter)
				return false;
			const ts = new Date(a.created_at).getTime();
			if (fromMs != null && ts < fromMs) return false;
			if (toMs != null && ts > toMs) return false;
			if (q) {
				const haystack = [
					a.monitor_name,
					a.monitor_url,
					a.ai_summary,
					a.diff_summary,
					a.change_category,
				]
					.filter(Boolean)
					.join(" ")
					.toLowerCase();
				if (!haystack.includes(q)) return false;
			}
			return true;
		});
	}, [alerts, query, monitorFilter, dateFrom, dateTo]);

	async function markRead(alert: AlertInboxItem, isRead = true) {
		if (!workspaceId) return;
		setBusy(true);
		setError(null);
		try {
			await api.markChangeRead(workspaceId, alert.id, isRead);
			await load(workspaceId, filter, limit);
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to update read state");
		} finally {
			setBusy(false);
		}
	}

	async function markAllRead() {
		if (!workspaceId) return;
		setBusy(true);
		setError(null);
		try {
			const sum = await api.markAllAlertsRead(workspaceId);
			setSummary(sum);
			await load(workspaceId, filter, limit);
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to mark all read");
		} finally {
			setBusy(false);
		}
	}

	async function toggleNoise(alert: AlertInboxItem) {
		if (!workspaceId) return;
		setBusy(true);
		setError(null);
		try {
			await api.markChangeNoise(workspaceId, alert.id, !alert.is_noise);
			await load(workspaceId, filter, limit);
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to update noise");
		} finally {
			setBusy(false);
		}
	}

	const signalCount = summary ? summary.total - summary.noise : 0;

	if (loading) return <Spinner />;

	return (
		<div>
			<PageHeader
				title="Alerts"
				description="Every detected change across your monitors — summarized by AI and triaged against your watch notes."
				actions={
					<Button
						type="button"
						variant="secondary"
						disabled={busy || !summary?.unread}
						onClick={markAllRead}
					>
						Mark all read
						{summary && summary.unread > 0 ? ` (${summary.unread})` : ""}
					</Button>
				}
			/>
			{error ? <ErrorBox message={error} /> : null}

			<div className="mb-6">
				<SegmentedControl<Filter>
					ariaLabel="Alert filter"
					value={filter}
					onChange={(key) => {
						setFilter(key);
						setLimit(PAGE_SIZE);
					}}
					options={[
						{
							value: "all",
							label: `Signal${summary ? ` · ${signalCount}` : ""}`,
						},
						{
							value: "unread",
							label: `Unread${summary ? ` · ${summary.unread}` : ""}`,
						},
						{
							value: "noise",
							label: `Noise${summary ? ` · ${summary.noise}` : ""}`,
						},
					]}
				/>
			</div>

			<div className="mb-6 flex flex-wrap items-center gap-2">
				<Input
					type="search"
					value={query}
					onChange={(e) => setQuery(e.target.value)}
					placeholder="Search alerts…"
					aria-label="Search alerts"
					className="h-9 w-full max-w-xs"
				/>
				<div className="max-w-[14rem] flex-1">
					<Select
						value={monitorFilter}
						onChange={(e) => setMonitorFilter(e.target.value)}
						aria-label="Filter by monitor"
						className="h-9"
					>
						<option value="all">All monitors</option>
						{monitorOptions.map((m) => (
							<option key={m.id} value={m.id}>
								{m.name}
							</option>
						))}
					</Select>
				</div>
				<Input
					type="date"
					value={dateFrom}
					onChange={(e) => setDateFrom(e.target.value)}
					aria-label="From date"
					className="h-9 w-auto"
				/>
				<Input
					type="date"
					value={dateTo}
					onChange={(e) => setDateTo(e.target.value)}
					aria-label="To date"
					className="h-9 w-auto"
				/>
				{(query || monitorFilter !== "all" || dateFrom || dateTo) && (
					<Button
						type="button"
						variant="ghost"
						size="sm"
						onClick={() => {
							setQuery("");
							setMonitorFilter("all");
							setDateFrom("");
							setDateTo("");
						}}
					>
						Clear
					</Button>
				)}
			</div>

			{alerts.length === 0 ? (
				filter === "unread" && summary && summary.total > summary.noise ? (
					<EmptyState
						title="All caught up"
						body="You have no unread alerts. Switch to Signal to review past changes."
					/>
				) : (
					<EmptyState
						title="No alerts yet"
						body="When a monitor detects a content change, AI will summarize it here."
						action={
							<Link href="/monitors/new">
								<Button type="button">Create a monitor</Button>
							</Link>
						}
					/>
				)
			) : visibleAlerts.length === 0 ? (
				<EmptyState
					title="No matching alerts"
					body="No alerts match your current search or filters. Try clearing them."
				/>
			) : (
				<div className="space-y-2">
					{visibleAlerts.map((a) => {
						const headline = a.ai_summary || a.diff_summary || "Content changed";
						const reason = a.is_noise ? triageReason(a.ai_summary ?? null) : null;
						return (
							<Card
								key={a.id}
								className={
									a.is_read
										? "!py-0"
										: "!py-0 border-l-4 border-l-sky-500 bg-sky-500/[0.04] dark:bg-sky-500/[0.06]"
								}
							>
								<div className="flex items-start gap-3 p-4">
									<span
										className={`mt-1.5 h-3 w-3 shrink-0 rounded-full ${changeDotClass(
											a.change_category ?? null,
										)}`}
										aria-hidden
									/>
									<div className="min-w-0 flex-1">
										<div className="mb-1.5 flex flex-wrap items-center gap-2">
											{!a.is_read ? <Badge tone="info">unread</Badge> : null}
											{a.is_noise ? (
												<Badge tone="warn">noise</Badge>
											) : a.change_category ? (
												<Badge tone="neutral">
													{CATEGORY_LABEL[a.change_category] ??
														a.change_category}
												</Badge>
											) : null}
											<span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
												{a.monitor_name}
											</span>
										</div>
										<p className="text-[15px] font-medium leading-snug text-slate-800 dark:text-slate-100">
											{reason ?? headline}
										</p>
										{reason ? (
											<p className="mt-1 text-sm leading-relaxed text-slate-500 dark:text-slate-400 line-through decoration-slate-400/60">
												{headline}
											</p>
										) : null}
										<p className="mt-1.5 truncate text-xs text-slate-500 dark:text-slate-500">
											{a.monitor_url} · {relativeTime(a.created_at)}
										</p>
									</div>
									<div className="flex shrink-0 flex-wrap gap-2">
										<Button
											type="button"
											size="sm"
											disabled={busy}
											onClick={async () => {
												if (!a.is_read) await markRead(a, true);
												router.push(`/changes/${a.id}`);
											}}
										>
											Open
										</Button>
										<Button
											type="button"
											size="sm"
											variant="secondary"
											disabled={busy}
											onClick={() => markRead(a, !a.is_read)}
										>
											{a.is_read ? "Mark unread" : "Mark read"}
										</Button>
										<Button
											type="button"
											size="sm"
											variant="ghost"
											disabled={busy}
											onClick={() => toggleNoise(a)}
										>
											{a.is_noise ? "Unmark noise" : "Noise"}
										</Button>
									</div>
								</div>
							</Card>
						);
					})}
					{alerts.length >= limit ? (
						<div className="flex flex-col items-center gap-1.5 pt-3">
							<Button
								type="button"
								variant="secondary"
								disabled={loading || busy}
								onClick={() => setLimit((l) => l + PAGE_SIZE)}
							>
								Load more
							</Button>
							<p className="text-xs text-slate-500 dark:text-slate-500">
								Showing the first {alerts.length} alerts for this filter.
							</p>
						</div>
					) : null}
				</div>
			)}
		</div>
	);
}
