"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
	Badge,
	Button,
	Card,
	CategoryBadge,
	EmptyState,
	ErrorBox,
	Input,
	PageHeader,
	SegmentedControl,
	Select,
	Spinner,
} from "@/components/ui";
import { BrandLogo } from "@/components/brand-logo";
import { GithubDiff } from "@/components/github-diff";
import { useToast } from "@/components/toasts";
import { api } from "@/lib/api";
import type { AlertInboxItem, AlertsSummary, ChangeEventDetail } from "@/lib/types";
import { usePageTitle } from "@/lib/use-page-title";
import { ensureWorkspace } from "@/lib/workspace";
import { config } from "@/lib/config";

type Filter = "all" | "unread" | "noise";

const PAGE_SIZE = 100;

function relativeTime(iso: string): string {
	const ms = Date.now() - new Date(iso).getTime();
	const m = Math.floor(ms / 60000);
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

	// Cache of fetched diff details for inline expansion
	const [expandedDiffs, setExpandedDiffs] = useState<Record<string, ChangeEventDetail>>({});
	const [loadingDiffs, setLoadingDiffs] = useState<Record<string, boolean>>({});

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
	const toast = useToast();

	async function markRead(alert: AlertInboxItem, isRead = true) {
		if (!workspaceId) return;
		const prev = alerts;
		setAlerts((list) => list.map((a) => (a.id === alert.id ? { ...a, is_read: isRead } : a)));
		setError(null);
		try {
			await api.markChangeRead(workspaceId, alert.id, isRead);
			toast.success(isRead ? "Marked as read" : "Marked as unread", alert.monitor_name);
		} catch (e) {
			setAlerts(prev);
			const msg = e instanceof Error ? e.message : "Failed to update read state";
			setError(msg);
			toast.error("Could not update alert", msg);
		}
	}

	async function markAllRead() {
		if (!workspaceId) return;
		const prev = alerts;
		const prevSummary = summary;
		setAlerts((list) => list.map((a) => ({ ...a, is_read: true })));
		setBusy(true);
		setError(null);
		try {
			const sum = await api.markAllAlertsRead(workspaceId);
			setSummary(sum);
			await load(workspaceId, filter, limit);
			toast.success("Inbox cleared", "All alerts marked as read.");
		} catch (e) {
			setAlerts(prev);
			if (prevSummary) setSummary(prevSummary);
			const msg = e instanceof Error ? e.message : "Failed to mark all read";
			setError(msg);
			toast.error("Could not mark all read", msg);
		} finally {
			setBusy(false);
		}
	}

	async function toggleNoise(alert: AlertInboxItem) {
		if (!workspaceId) return;
		const prev = alerts;
		const nextNoise = !alert.is_noise;
		setAlerts((list) => list.map((a) => (a.id === alert.id ? { ...a, is_noise: nextNoise } : a)));
		setError(null);
		try {
			await api.markChangeNoise(workspaceId, alert.id, nextNoise);
			toast.success(nextNoise ? "Moved to noise" : "Restored to signal", alert.monitor_name);
			await load(workspaceId, filter, limit);
		} catch (e) {
			setAlerts(prev);
			const msg = e instanceof Error ? e.message : "Failed to update noise";
			setError(msg);
			toast.error("Could not update alert", msg);
		}
	}

	async function toggleInlineDiff(alert: AlertInboxItem) {
		if (!workspaceId) return;
		if (expandedDiffs[alert.id]) {
			// Collapse
			setExpandedDiffs((prev) => {
				const next = { ...prev };
				delete next[alert.id];
				return next;
			});
			return;
		}

		// Expand & load
		setLoadingDiffs((prev) => ({ ...prev, [alert.id]: true }));
		try {
			const detail = await api.getChange(workspaceId, alert.id);
			setExpandedDiffs((prev) => ({ ...prev, [alert.id]: detail }));
			if (!alert.is_read) {
				// Silent auto-read on expand — no toast, revert silently on failure.
				setAlerts((list) => list.map((a) => (a.id === alert.id ? { ...a, is_read: true } : a)));
				try {
					await api.markChangeRead(workspaceId, alert.id, true);
				} catch {
					setAlerts((list) => list.map((a) => (a.id === alert.id ? { ...a, is_read: false } : a)));
				}
			}
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to load diff");
		} finally {
			setLoadingDiffs((prev) => ({ ...prev, [alert.id]: false }));
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
					<div className="flex items-center gap-2">
						<Button
							type="button"
							variant="secondary"
							onClick={() => {
								if (!workspaceId) return;
								window.open(
									`${config.apiBaseUrl}/api/v1/workspaces/${workspaceId}/export/changes`,
									"_blank",
								);
							}}
						>
							Export JSON
						</Button>
						<Button
							type="button"
							variant="secondary"
							disabled={busy || !summary?.unread}
							onClick={markAllRead}
						>
							Mark all read
							{summary && summary.unread > 0 ? ` (${summary.unread})` : ""}
						</Button>
					</div>
				}
			/>
			{error ? <ErrorBox message={error} /> : null}

			{/* Filter Tabs */}
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

			{/* Search & Secondary Filters */}
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

			{/* Alerts Feed */}
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
				<div className="space-y-3">
					{visibleAlerts.map((a) => {
						const headline = a.ai_summary || a.diff_summary || "Content changed";
						const reason = a.is_noise ? triageReason(a.ai_summary ?? null) : null;
						const isExpanded = Boolean(expandedDiffs[a.id]);
						const isLoadingDiff = Boolean(loadingDiffs[a.id]);
						const diffDetail = expandedDiffs[a.id];

						return (
							<Card
								key={a.id}
								className={`transition-all ${
									a.is_read
										? "!p-0 border border-[var(--border)]"
										: "!p-0 border-l-4 border-l-[var(--accent)] bg-[var(--accent)]/[0.04] "
								}`}
							>
								{/* Alert Header Row */}
								<div className="flex flex-wrap items-start justify-between gap-3 p-4">
									<div className="flex items-start gap-3 min-w-0 flex-1">
										{/* Brand / Favicon Logo */}
										<BrandLogo
											brand={a.monitor_brand ?? null}
											name={a.monitor_name}
											domain={a.monitor_url}
											size={32}
											className="mt-0.5"
										/>

										<div className="min-w-0 flex-1">
											{/* Top Badges & Monitor Name */}
											<div className="mb-1.5 flex flex-wrap items-center gap-2">
												{!a.is_read ? <Badge tone="info">unread</Badge> : null}
												{a.is_noise ? (
													<Badge tone="warn">noise</Badge>
												) : (
													<CategoryBadge category={a.change_category} />
												)}
												<Link
													href={`/monitors/${a.monitor_id}`}
													className="text-sm font-semibold text-[var(--fg)] hover:text-[var(--accent)] truncate"
												>
													{a.monitor_name}
												</Link>
												<span className="text-xs text-slate-400 dark:text-slate-500">·</span>
												<span className="text-xs text-slate-500 dark:text-slate-400">
													{relativeTime(a.created_at)}
												</span>
											</div>

											{/* AI Summary / Headline */}
											<p className="text-[15px] font-medium leading-snug text-[var(--fg)]">
												{reason ?? headline}
											</p>
											{reason ? (
												<p className="mt-1 text-sm leading-relaxed text-slate-500 dark:text-slate-400 line-through decoration-slate-400/60">
													{headline}
												</p>
											) : null}

											{/* Monitor URL subtitle */}
											<p className="mt-1.5 truncate text-xs text-slate-500 dark:text-slate-500">
												{a.monitor_url}
											</p>
										</div>
									</div>

									{/* Action Buttons */}
									<div className="flex shrink-0 items-center gap-1.5 self-start pt-1">
										{/* Toggle Diff Preview Button */}
										<Button
											type="button"
											size="sm"
											variant={isExpanded ? "secondary" : "primary"}
											disabled={busy || isLoadingDiff}
											onClick={() => toggleInlineDiff(a)}
											className="text-xs font-medium"
										>
											{isLoadingDiff
												? "Loading…"
												: isExpanded
												? "Hide diff"
												: "Show changes"}
										</Button>

										{/* Mark Read/Unread */}
										<Button
											type="button"
											size="sm"
											variant="ghost"
											disabled={busy}
											onClick={() => markRead(a, !a.is_read)}
											title={a.is_read ? "Mark unread" : "Mark read"}
											className="text-xs"
										>
											{a.is_read ? "Unread" : "Read"}
										</Button>

										{/* Noise Toggle */}
										<Button
											type="button"
											size="sm"
											variant="ghost"
											disabled={busy}
											onClick={() => toggleNoise(a)}
											title={a.is_noise ? "Restore to signal" : "Mark as noise"}
											className="text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400"
										>
											{a.is_noise ? "Signal" : "Noise"}
										</Button>

										{/* Direct link to detail page */}
										<Link href={`/changes/${a.id}`}>
											<Button type="button" size="sm" variant="ghost" className="text-xs">
												Full page ↗
											</Button>
										</Link>
									</div>
								</div>

								{/* Inline Diff Accordion View */}
								{isExpanded && diffDetail ? (
									<div className="border-t border-[var(--border)] bg-slate-50/50 p-4 dark:bg-slate-900/30">
										<GithubDiff
											before={diffDetail.previous_text}
											after={diffDetail.new_text}
											unifiedDiff={diffDetail.diff}
											baseUrl={a.monitor_url}
										/>
									</div>
								) : null}
							</Card>
						);
					})}

					{/* Pagination / Load more */}
					{alerts.length >= limit ? (
						<div className="flex flex-col items-center gap-1.5 pt-4">
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
