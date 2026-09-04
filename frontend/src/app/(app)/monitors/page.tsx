"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
	Badge,
	Button,
	EmptyState,
	ErrorBox,
	Input,
	ModeBadge,
	PageHeader,
	SegmentedControl,
	Select,
} from "@/components/ui";
import { useToast } from "@/components/toasts";
import { BrandLogo } from "@/components/brand-logo";
import { SkeletonTable } from "@/components/skeleton";
import { api } from "@/lib/api";
import type { Monitor, MonitorMode } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";
import { config } from "@/lib/config";

type StatusFilter = "all" | "active" | "paused";
type SortKey = "name" | "schedule";
type SortDir = "asc" | "desc";

const MODE_OPTIONS: Array<{ value: MonitorMode | "all"; label: string }> = [
	{ value: "all", label: "All modes" },
	{ value: "page_content", label: "Page content" },
	{ value: "site_links", label: "Site links" },
	{ value: "product_price", label: "Product price" },
	{ value: "list_items", label: "List items" },
	{ value: "json_field", label: "JSON field" },
	{ value: "rss_feed", label: "RSS feed" },
	{ value: "readme", label: "GitHub README" },
	{ value: "visual", label: "Visual diff" },
];

/** Last-check time: latest_change.created_at when present, else next_run_at. */
function lastCheckKey(m: Monitor): number {
	const raw = m.latest_change?.created_at ?? m.next_run_at;
	const t = Date.parse(raw);
	return Number.isNaN(t) ? 0 : t;
}

export default function MonitorsPage() {
	usePageTitle("Monitors");
	const router = useRouter();
	const toast = useToast();
	const [monitors, setMonitors] = useState<Monitor[]>([]);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);
	const [selected, setSelected] = useState<Set<string>>(new Set());
	const [bulkBusy, setBulkBusy] = useState(false);
	const [query, setQuery] = useState("");
	const [modeFilter, setModeFilter] = useState<MonitorMode | "all">("all");
	const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
	const [sortKey, setSortKey] = useState<SortKey>("name");
	const [sortDir, setSortDir] = useState<SortDir>("asc");

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const ws = await ensureWorkspace();
				const list = await api.listMonitors(ws);
				if (!cancelled) setMonitors(list);
			} catch (e) {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load monitors");
			} finally {
				if (!cancelled) setLoading(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, []);

	const filtered = useMemo(() => {
		const q = query.trim().toLowerCase();
		const out = monitors.filter((m) => {
			if (modeFilter !== "all" && m.mode !== modeFilter) return false;
			if (statusFilter === "active" && !m.enabled) return false;
			if (statusFilter === "paused" && m.enabled) return false;
			if (
				q &&
				!m.name.toLowerCase().includes(q) &&
				!m.url.toLowerCase().includes(q)
			)
				return false;
			return true;
		});
		const dir = sortDir === "asc" ? 1 : -1;
		out.sort((a, b) => {
			if (sortKey === "schedule") return (lastCheckKey(a) - lastCheckKey(b)) * dir;
			return (
				a.name.localeCompare(b.name, undefined, { sensitivity: "base" }) * dir
			);
		});
		return out;
	}, [monitors, query, modeFilter, statusFilter, sortKey, sortDir]);

	if (loading) return <SkeletonTable rows={6} />;

	const toggle = (id: string) => {
		setSelected((prev) => {
			const next = new Set(prev);
			if (next.has(id)) next.delete(id);
			else next.add(id);
			return next;
		});
	};
	const toggleAllFiltered = () => {
		setSelected((prev) => {
			const next = new Set(prev);
			const everySelected =
				filtered.length > 0 && filtered.every((m) => next.has(m.id));
			if (everySelected) filtered.forEach((m) => next.delete(m.id));
			else filtered.forEach((m) => next.add(m.id));
			return next;
		});
	};
	const runBulk = async (action: string) => {
		if (selected.size === 0) return;
		setBulkBusy(true);
		try {
			const ws = await ensureWorkspace();
			await api.bulkAction(ws, { monitor_ids: Array.from(selected), action });
			const list = await api.listMonitors(ws);
			setMonitors(list);
			setSelected(new Set());
			toast.success(`Bulk ${action} complete`);
		} catch (e) {
			const message = e instanceof Error ? e.message : "Bulk action failed";
			setError(message);
			toast.error("Bulk action failed", message);
		} finally {
			setBulkBusy(false);
		}
	};
	const filtersActive =
		query.trim() !== "" || modeFilter !== "all" || statusFilter !== "all";
	const clearFilters = () => {
		setQuery("");
		setModeFilter("all");
		setStatusFilter("all");
		setSortKey("name");
		setSortDir("asc");
	};
	const toggleSort = (key: SortKey) => {
		if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
		else {
			setSortKey(key);
			setSortDir("asc");
		}
	};
	const allFilteredSelected =
		filtered.length > 0 && filtered.every((m) => selected.has(m.id));

	return (
		<div>
			<PageHeader
				title="Monitors"
				description="All page checks in this workspace."
				actions={
					<div className="flex items-center gap-2">
						<Button
							type="button"
							variant="secondary"
							onClick={async () => {
								const ws = await ensureWorkspace();
								window.open(
									`${config.apiBaseUrl}/api/v1/workspaces/${ws}/export/monitors?format=csv`,
									"_blank",
								);
							}}
						>
							Export CSV
						</Button>
						<Link href="/monitors/new">
							<Button type="button">
								<svg
									className="h-4 w-4"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									strokeWidth={2}
								>
									<path
										strokeLinecap="round"
										strokeLinejoin="round"
										d="M12 4.5v15m7.5-7.5h-15"
									/>
								</svg>
								New monitor
							</Button>
						</Link>
					</div>
				}
			/>
			{error ? <ErrorBox message={error} /> : null}

			{selected.size > 0 && (
				<div className="mb-3 flex items-center gap-2 rounded-xl border bg-amber-50 dark:bg-amber-900/20 p-2 text-sm">
					<span>{selected.size} selected</span>
					<Button size="sm" variant="secondary" disabled={bulkBusy} onClick={() => runBulk("pause")}>Pause</Button>
					<Button size="sm" variant="secondary" disabled={bulkBusy} onClick={() => runBulk("resume")}>Resume</Button>
					<Button size="sm" variant="danger" disabled={bulkBusy} onClick={() => runBulk("delete")}>Delete</Button>
					<Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
				</div>
			)}
			{monitors.length === 0 ? (
				<EmptyState
					title="No monitors"
					body="Create a monitor for a public URL or CSS selector section."
					action={
						<Link href="/monitors/new">
							<Button type="button">Create monitor</Button>
						</Link>
					}
				/>
			) : (
				<>
					<div className="mb-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
						<Input
							type="search"
							placeholder="Search name or URL…"
							aria-label="Search monitors"
							value={query}
							onChange={(e) => setQuery(e.target.value)}
							className="sm:max-w-xs"
						/>
						<Select
							aria-label="Filter by mode"
							value={modeFilter}
							onChange={(e) =>
								setModeFilter(e.target.value as MonitorMode | "all")
							}
							className="sm:w-auto"
						>
							{MODE_OPTIONS.map((o) => (
								<option key={o.value} value={o.value}>
									{o.label}
								</option>
							))}
						</Select>
						<SegmentedControl<StatusFilter>
							ariaLabel="Filter by status"
							value={statusFilter}
							onChange={setStatusFilter}
							options={[
								{ value: "all", label: "All" },
								{ value: "active", label: "Active" },
								{ value: "paused", label: "Paused" },
							]}
						/>
						<div className="flex items-center gap-2 text-sm text-[var(--muted)] sm:ml-auto">
							<span aria-live="polite">
								{filtered.length} of {monitors.length} monitor
								{monitors.length === 1 ? "" : "s"}
							</span>
							{filtersActive && (
								<Button
									type="button"
									size="sm"
									variant="ghost"
									onClick={clearFilters}
								>
									Clear
								</Button>
							)}
						</div>
					</div>
					{filtered.length === 0 ? (
						<EmptyState
							title="No monitors match"
							body="Try a different search term or clear the filters."
							action={
								<Button type="button" variant="secondary" onClick={clearFilters}>
									Clear filters
								</Button>
							}
						/>
					) : (
						<>
							{/* Desktop table */}
							<div className="hidden md:block">
								<div className="surface overflow-hidden">
									<div className="overflow-x-auto">
										<table className="w-full text-left text-sm">
											<thead>
												<tr className="border-b border-[var(--border)] bg-[var(--surface-bg)]">
													<th className="px-2 py-3">
														<input
															type="checkbox"
															aria-label="Select all monitors"
															checked={allFilteredSelected}
															onChange={toggleAllFiltered}
														/>
													</th>
													<th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
														<button
															type="button"
															onClick={() => toggleSort("name")}
															aria-label={`Sort by name (${sortKey === "name" && sortDir === "asc" ? "descending" : "ascending"})`}
															className="uppercase tracking-[0.12em] hover:text-[var(--text)]"
														>
															Name
															<span aria-hidden="true">
																{sortKey === "name" ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
															</span>
														</button>
													</th>
													<th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
														URL
													</th>
													<th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
														Mode
													</th>
													<th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
														<button
															type="button"
															onClick={() => toggleSort("schedule")}
															aria-label={`Sort by schedule (${sortKey === "schedule" && sortDir === "asc" ? "descending" : "ascending"})`}
															className="uppercase tracking-[0.12em] hover:text-[var(--text)]"
														>
															Schedule
															<span aria-hidden="true">
																{sortKey === "schedule" ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
															</span>
														</button>
													</th>
													<th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
														Status
													</th>
												</tr>
											</thead>
											<tbody className="divide-y divide-[var(--border)]">
												{filtered.map((m) => (
													<tr
														key={m.id}
														className="cursor-pointer transition hover:bg-slate-100/60 dark:hover:bg-white/[0.03]"
														onClick={() => router.push(`/monitors/${m.id}`)}
													>
														<td className="px-2 py-3.5" onClick={(e) => e.stopPropagation()}>
															<input
																type="checkbox"
																aria-label={`Select ${m.name}`}
																checked={selected.has(m.id)}
																onChange={() => toggle(m.id)}
															/>
														</td>
														<td className="px-4 py-3.5">
															<div className="flex items-center gap-2.5">
																<BrandLogo brand={m.brand} name={m.name} domain={m.url} size={24} />
																<Link
																	href={`/monitors/${m.id}`}
																	className="font-medium text-slate-900 hover:text-[var(--accent)] dark:text-slate-100"
																>
																	{m.name}
																</Link>
															</div>
														</td>
														<td className="max-w-xs truncate px-4 py-3.5 text-slate-600 dark:text-slate-400">
															{m.url}
														</td>
														<td className="px-4 py-3.5">
															<ModeBadge mode={m.mode} />
														</td>
														<td className="px-4 py-3.5 text-slate-600 dark:text-slate-400">
															every {m.schedule_interval_minutes}m
														</td>
														<td className="px-4 py-3.5">
															<Badge tone={m.enabled ? "success" : "warn"}>
																{m.enabled ? "active" : "paused"}
															</Badge>
														</td>
													</tr>
												))}
											</tbody>
										</table>
									</div>
								</div>
							</div>

							{/* Mobile cards */}
							<div className="space-y-2 md:hidden">
								{filtered.map((m) => (
									<div
										key={m.id}
										role="link"
										tabIndex={0}
										aria-label={m.name}
										onClick={() => router.push(`/monitors/${m.id}`)}
										onKeyDown={(e) => {
											if (e.key === "Enter" || e.key === " ") {
												e.preventDefault();
												router.push(`/monitors/${m.id}`);
											}
										}}
										className="glass-card !p-4 transition cursor-pointer hover:border-[var(--accent)]/40 dark:hover:border-[var(--accent)]/20"
									>
										<div className="flex items-start justify-between gap-2">
											<div className="flex items-center gap-2.5 min-w-0">
												<span onClick={(e) => e.stopPropagation()}>
													<input
														type="checkbox"
														aria-label={`Select ${m.name}`}
														checked={selected.has(m.id)}
														onChange={() => toggle(m.id)}
														onClick={(e) => e.stopPropagation()}
													/>
												</span>
												<BrandLogo brand={m.brand} name={m.name} domain={m.url} size={24} />
												<p className="truncate font-medium text-[var(--fg)]">
													{m.name}
												</p>
											</div>
											<Badge tone={m.enabled ? "success" : "warn"}>
												{m.enabled ? "active" : "paused"}
											</Badge>
										</div>
										<p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-500">
											{m.url}
										</p>
										<div className="mt-3 flex flex-wrap gap-2">
											<ModeBadge mode={m.mode} />
											<Badge tone="neutral">{m.schedule_interval_minutes}m</Badge>
										</div>
									</div>
								))}
							</div>
						</>
					)}
				</>
			)}
		</div>
	);
}
