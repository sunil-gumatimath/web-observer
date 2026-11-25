"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
	Badge,
	Button,
	Card,
	CategoryBadge,
	EmptyState,
	ErrorBox,
	ImpactBadge,
	Input,
	PageHeader,
	SegmentedControl,
	Select,
	Spinner,
	parseImpact,
} from "@/components/ui";
import { BrandLogo } from "@/components/brand-logo";
import { GithubDiff } from "@/components/github-diff";
import { useToast } from "@/components/toasts";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { AlertInboxItem, AlertsSummary, ChangeEventDetail, Monitor } from "@/lib/types";
import { usePageTitle } from "@/lib/use-page-title";
import { ensureWorkspace } from "@/lib/workspace";
import { fetchCached, invalidateCachePrefix, readCache } from "@/lib/query-cache";
import { cacheKeys } from "@/lib/route-prefetch";
import { useAutoRefresh } from "@/lib/use-auto-refresh";
import {
  alertTabTotal,
  canLoadMoreAlerts,
  nextAlertLimit,
} from "@/lib/alerts-pagination";
import { exportFileName, triggerBlobDownload } from "@/lib/download";
import { composeHeadline, parseSummaryParts } from "@/lib/summary";

type Filter = "all" | "unread" | "noise";
type ImpactFilter = "all" | "high" | "medium" | "low";

const PAGE_SIZE = 100;

/** Normalized impact level: critical folds into high. Null when unknown. */
function impactLevel(a: AlertInboxItem): ImpactFilter | null {
	const raw = (a.impact ?? parseImpact(a.ai_summary) ?? "").toLowerCase();
	if (!raw) return null;
	if (raw === "critical") return "high";
	if (raw === "high" || raw === "medium" || raw === "low") return raw;
	return null;
}

/** Filter raw `include_noise: true` / `unread_only` alerts for the active tab. */
function filterAlertsForTab(list: AlertInboxItem[], f: Filter): AlertInboxItem[] {
	if (f === "noise") return list.filter((a) => a.is_noise);
	if (f === "all") return list.filter((a) => !a.is_noise);
	return list;
}

async function fetchAlertsTabData(ws: string, f: Filter, lim: number, force = false) {
	const opts = { force, maxAgeMs: force ? 0 : 4_000 };
	const listKey =
		f === "unread"
			? cacheKeys.alertsUnread(ws, lim)
			: cacheKeys.alertsWithNoise(ws, lim);
	const [rawList, sum, mons] = await Promise.all([
		fetchCached(
			listKey,
			() =>
				api.listAlerts(ws, {
					unread_only: f === "unread",
					include_noise: f === "noise" || f === "all",
					limit: lim,
				}),
			opts,
		),
		fetchCached(cacheKeys.alertsSummary(ws), () => api.alertsSummary(ws), opts),
		fetchCached(
			cacheKeys.monitors(ws),
			() => api.listMonitors(ws).catch(() => []),
			{ force, maxAgeMs: force ? 0 : 15_000 },
		),
	]);
	return {
		items: filterAlertsForTab(rawList, f),
		sum,
		mons,
	};
}

export default function AlertsPage() {
	usePageTitle("Alerts");
	const initialWs = readCache<string>("activeWorkspaceId")?.data ?? null;
	const initialRawAlerts = initialWs
		? readCache<AlertInboxItem[]>(cacheKeys.alertsWithNoise(initialWs, PAGE_SIZE))
		: undefined;
	const initialSummary = initialWs
		? readCache<AlertsSummary | null>(cacheKeys.alertsSummary(initialWs))?.data ?? null
		: null;
	const initialMonitors = initialWs
		? readCache<Monitor[]>(cacheKeys.monitors(initialWs))?.data
		: undefined;

	const [workspaceId, setWorkspaceId] = useState<string | null>(initialWs);
	const [alerts, setAlerts] = useState<AlertInboxItem[]>(
		initialRawAlerts ? filterAlertsForTab(initialRawAlerts.data, "all") : [],
	);
	const [monitors, setMonitors] = useState<Monitor[]>(initialMonitors ?? []);
	const [summary, setSummary] = useState<AlertsSummary | null>(initialSummary);
	const [filter, setFilter] = useState<Filter>("all");
	const [query, setQuery] = useState("");
	const [monitorFilter, setMonitorFilter] = useState<string>("all");
	const [impactFilter, setImpactFilter] = useState<ImpactFilter>("all");
	const [dateFrom, setDateFrom] = useState("");
	const [dateTo, setDateTo] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(!initialRawAlerts);
	const [busy, setBusy] = useState(false);
	const [limit, setLimit] = useState(PAGE_SIZE);
	const [exporting, setExporting] = useState(false);
	const [refreshTick, setRefreshTick] = useState(0);
	const [lastUpdated, setLastUpdated] = useState<Date | null>(
		initialRawAlerts ? new Date(initialRawAlerts.updatedAt) : null,
	);

	// Cache of fetched diff details for inline expansion
	const [expandedDiffs, setExpandedDiffs] = useState<Record<string, ChangeEventDetail>>({});
	const [loadingDiffs, setLoadingDiffs] = useState<Record<string, boolean>>({});

	async function load(ws: string, f: Filter, lim: number, force = false) {
		const { items, sum, mons } = await fetchAlertsTabData(ws, f, lim, force);
		setAlerts(items);
		setSummary(sum);
		setMonitors(mons);
	}

	useEffect(() => {
		let cancelled = false;
		const force = refreshTick > 0;
		(async () => {
			try {
				const ws = await ensureWorkspace();
				if (cancelled) return;
				setWorkspaceId(ws);
				const { items, sum, mons } = await fetchAlertsTabData(ws, filter, limit, force);
				if (cancelled) return;
				setAlerts(items);
				setSummary(sum);
				setMonitors(mons);
				setLastUpdated(new Date());
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
	}, [filter, limit, refreshTick]);

	// 15s cadence plus an immediate refresh on tab focus/visibility; the old
	// flat 60s timer left new alerts invisible for up to a minute.
	useAutoRefresh(() => setRefreshTick((n) => n + 1));

	// Distinct monitors in the workspace + inbox, for the monitor filter dropdown.
	const monitorOptions = useMemo(() => {
		const counts = new Map<string, number>();
		for (const a of alerts) {
			counts.set(a.monitor_id, (counts.get(a.monitor_id) ?? 0) + 1);
		}
		const seen = new Map<string, { id: string; name: string; count: number }>();
		for (const m of monitors) {
			seen.set(m.id, { id: m.id, name: m.name, count: counts.get(m.id) ?? 0 });
		}
		for (const a of alerts) {
			if (!seen.has(a.monitor_id)) {
				seen.set(a.monitor_id, {
					id: a.monitor_id,
					name: a.monitor_name,
					count: counts.get(a.monitor_id) ?? 1,
				});
			}
		}
		return [...seen.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
	}, [alerts, monitors]);

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
			if (impactFilter !== "all" && impactLevel(a) !== impactFilter)
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
	}, [alerts, query, monitorFilter, impactFilter, dateFrom, dateTo]);
	const toast = useToast();

	async function markRead(alert: AlertInboxItem, isRead = true) {
		if (!workspaceId) return;
		const prev = alerts;
		setAlerts((list) => list.map((a) => (a.id === alert.id ? { ...a, is_read: isRead } : a)));
		setError(null);
		try {
			await api.markChangeRead(workspaceId, alert.id, isRead);
			invalidateCachePrefix(`alertsWithNoise:${workspaceId}:`);
			invalidateCachePrefix(`alertsUnread:${workspaceId}:`);
			invalidateCachePrefix(`alertsSummary:${workspaceId}`);
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
			invalidateCachePrefix(`alertsWithNoise:${workspaceId}:`);
			invalidateCachePrefix(`alertsUnread:${workspaceId}:`);
			await load(workspaceId, filter, limit, true);
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
			invalidateCachePrefix(`alertsWithNoise:${workspaceId}:`);
			invalidateCachePrefix(`alertsUnread:${workspaceId}:`);
			await load(workspaceId, filter, limit, true);
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
	// Gate "Load more" on the tab's unfiltered total, not on the length of the
	// filtered page (noise/search/monitor/impact/date can hide most of it).
	const tabTotal = alertTabTotal(summary, filter);
	const showLoadMore = canLoadMoreAlerts(limit, tabTotal);

	async function exportChanges() {
		if (!workspaceId || exporting) return;
		setExporting(true);
		setError(null);
		try {
			const blob = await api.exportChanges(workspaceId);
			triggerBlobDownload(blob, exportFileName("changes", "json"));
		} catch (e) {
			const message = e instanceof Error ? e.message : "Failed to export changes";
			setError(message);
			toast.error("Could not export changes", message);
		} finally {
			setExporting(false);
		}
	}

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
							disabled={exporting || !workspaceId}
							onClick={exportChanges}
						>
							{exporting ? "Exporting…" : "Export JSON"}
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
						if (workspaceId) {
							const keyCache =
								key === "unread"
									? cacheKeys.alertsUnread(workspaceId, PAGE_SIZE)
									: cacheKeys.alertsWithNoise(workspaceId, PAGE_SIZE);
							const cached = readCache<AlertInboxItem[]>(keyCache);
							if (cached) {
								setAlerts(filterAlertsForTab(cached.data, key));
							}
						}
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
				<div className="w-full sm:w-60 sm:shrink-0">
					<Select
						value={monitorFilter}
						onChange={(e) => setMonitorFilter(e.target.value)}
						aria-label="Filter by monitor"
						className="h-9 w-full"
					>
						<option value="all">All monitors ({monitors.length || monitorOptions.length})</option>
						{monitorOptions.map((m) => (
							<option key={m.id} value={m.id}>
								{m.name} {m.count > 0 ? `(${m.count})` : `(0 alerts)`}
							</option>
						))}
					</Select>
				</div>
				<div className="w-full sm:w-44 sm:shrink-0">
					<Select
						value={impactFilter}
						onChange={(e) => setImpactFilter(e.target.value as ImpactFilter)}
						aria-label="Filter by impact"
						className="h-9 w-full"
					>
						<option value="all">All impacts</option>
						<option value="high">High impact</option>
						<option value="medium">Medium impact</option>
						<option value="low">Low impact</option>
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
				{(query || monitorFilter !== "all" || impactFilter !== "all" || dateFrom || dateTo) && (
					<Button
						type="button"
						variant="ghost"
						size="sm"
						onClick={() => {
							setQuery("");
							setMonitorFilter("all");
							setImpactFilter("all");
							setDateFrom("");
							setDateTo("");
						}}
					>
						Clear
					</Button>
				)}
				<div className="ml-auto flex items-center gap-2 text-xs text-[var(--ink-subtle)]">
					{lastUpdated ? (
						<span title={lastUpdated.toLocaleString()}>
							Updated {relativeTime(lastUpdated.toISOString())}
						</span>
					) : null}
					<Button
						type="button"
						size="sm"
						variant="ghost"
						onClick={() => setRefreshTick((n) => n + 1)}
					>
						Refresh
					</Button>
				</div>
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
						body={
							monitors.length > 0
								? `You have ${monitors.length} active monitor${monitors.length === 1 ? "" : "s"} running. The first check captures the baseline without an alert. When a content change is detected on a future check, an AI summary and alert will appear here.`
								: "When a monitor detects a content change, AI will summarize it here."
						}
						action={
							monitors.length > 0 ? (
								<div className="flex flex-wrap items-center justify-center gap-2">
									<Link href="/monitors">
										<Button type="button">View monitors ({monitors.length})</Button>
									</Link>
									<Link href="/monitors/new">
										<Button type="button" variant="secondary">Create another monitor</Button>
									</Link>
								</div>
							) : (
								<Link href="/monitors/new">
									<Button type="button">Create a monitor</Button>
								</Link>
							)
						}
					/>
				)
			) : visibleAlerts.length === 0 ? (
				monitorFilter !== "all" ? (() => {
					const selMon = monitors.find((m) => m.id === monitorFilter);
					return (
						<EmptyState
							title={`No alerts for ${selMon ? `"${selMon.name}"` : "this monitor"}`}
							body={
								filter === "noise"
									? "No noise held for this monitor. Switch to Signal to check for high-signal alerts."
									: filter === "unread"
										? "No unread alerts for this monitor. Switch to Signal to review past alerts."
										: "This monitor has not detected any content changes yet. The initial check captured the baseline; alerts appear here automatically as soon as a change is detected."
							}
							action={
								<div className="flex flex-wrap items-center justify-center gap-2">
									<Link href={`/monitors/${monitorFilter}`}>
										<Button type="button">View monitor details</Button>
									</Link>
									<Button
										type="button"
										variant="secondary"
										onClick={() => {
											setMonitorFilter("all");
										}}
									>
										Show all monitors
									</Button>
								</div>
							}
						/>
					);
				})() : (
					<EmptyState
						title="No matching alerts"
						body="No alerts match your current search or filters. Try clearing them."
						action={
							<Button
								type="button"
								variant="secondary"
								onClick={() => {
									setQuery("");
									setMonitorFilter("all");
									setImpactFilter("all");
									setDateFrom("");
									setDateTo("");
								}}
							>
								Clear filters
							</Button>
						}
					/>
				)
			) : (
				<div className="space-y-3">
					{visibleAlerts.map((a) => {
						const parts = parseSummaryParts(a.ai_summary);
						const reason = a.is_noise ? parts.reason : null;
						const headline = reason ?? composeHeadline(parts, a.title);
						const isExpanded = Boolean(expandedDiffs[a.id]);
						const isLoadingDiff = Boolean(loadingDiffs[a.id]);
						const diffDetail = expandedDiffs[a.id];

						return (
							<Card
								key={a.id}
								className={`transition-all ${
									a.is_read
										? "!p-0 border border-[var(--hairline)]"
										: "!p-0 border border-[var(--hairline-strong)] bg-[var(--surface-2)]/40"
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
												{a.is_noise ? null : (
													<ImpactBadge impact={a.impact ?? parseImpact(a.ai_summary)} />
												)}
												<Link
													href={`/monitors/${a.monitor_id}`}
													className="text-sm font-semibold text-[var(--fg)] hover:text-[var(--primary)] truncate"
												>
													{a.monitor_name}
												</Link>
												<span className="text-xs text-[var(--ink-tertiary)]">·</span>
												<span className="text-xs text-[var(--ink-subtle)]">
													{relativeTime(a.created_at)}
												</span>
											</div>

											{/* AI Summary / Headline */}
											<p
												className="text-[15px] font-medium leading-snug text-[var(--fg)] line-clamp-3"
												title={reason ?? headline}
											>
												{reason ?? headline}
											</p>
											{reason ? (
												<p className="mt-1 text-sm leading-relaxed text-[var(--ink-subtle)] line-through decoration-[var(--hairline-strong)]">
													{parts.detail || a.diff_summary || "Content changed"}
												</p>
											) : null}

											{/* Monitor URL subtitle */}
											<p className="mt-1.5 truncate text-xs text-[var(--ink-subtle)]">
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
											className="text-xs text-[var(--ink-subtle)] hover:text-[var(--ink)]"
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
									<div className="border-t border-[var(--hairline)] bg-[var(--surface-2)] p-4">
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

					{/* Pagination / Load more — based on the unfiltered tab total */}
					{showLoadMore ? (
						<div className="flex flex-col items-center gap-1.5 pt-4">
							<Button
								type="button"
								variant="secondary"
								disabled={loading || busy}
								onClick={() => setLimit((l) => nextAlertLimit(l, tabTotal))}
							>
								Load more
							</Button>
							<p className="text-xs text-[var(--ink-subtle)]">
								Showing the first {alerts.length} alerts for this filter of {tabTotal} total.
							</p>
						</div>
					) : null}
				</div>
			)}
		</div>
	);
}
