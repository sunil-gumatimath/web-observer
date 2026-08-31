"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
	Badge,
	Button,
	DataTable,
	EmptyState,
	ErrorBox,
	ModeBadge,
	PageHeader,
} from "@/components/ui";
import { BrandLogo } from "@/components/brand-logo";
import { SkeletonTable } from "@/components/skeleton";
import { api } from "@/lib/api";
import type { Monitor } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

export default function MonitorsPage() {
	usePageTitle("Monitors");
	const router = useRouter();
	const [monitors, setMonitors] = useState<Monitor[]>([]);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);
	const [selected, setSelected] = useState<Set<string>>(new Set());
	const [bulkBusy, setBulkBusy] = useState(false);

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

	if (loading) return <SkeletonTable rows={6} />;

	const toggle = (id: string) => {
		setSelected((prev) => {
			const next = new Set(prev);
			if (next.has(id)) next.delete(id);
			else next.add(id);
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
		} catch (e) {
			setError(e instanceof Error ? e.message : "Bulk action failed");
		} finally {
			setBulkBusy(false);
		}
	};

	return (
		<div>
			<PageHeader
				title="Monitors"
				description="All page checks in this workspace."
				actions={
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
					{/* Desktop table */}
					<div className="hidden md:block">
						<DataTable headers={["", "Name", "URL", "Mode", "Schedule", "Status"]}>
							{monitors.map((m) => (
								<tr
									key={m.id}
									className="cursor-pointer transition hover:bg-slate-100/60 dark:hover:bg-white/[0.03]"
									onClick={() => router.push(`/monitors/${m.id}`)}
								>
									<td className="px-2 py-3.5" onClick={(e) => e.stopPropagation()}>
										<input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} />
									</td>
									<td className="px-4 py-3.5">
										<div className="flex items-center gap-2.5">
											<BrandLogo brand={m.brand} name={m.name} domain={m.url} size={24} />
											<Link
												href={`/monitors/${m.id}`}
												className="font-medium text-slate-900 hover:text-sky-600 dark:text-slate-100 dark:hover:text-sky-300"
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
						</DataTable>
					</div>

					{/* Mobile cards */}
					<div className="space-y-2 md:hidden">
						{monitors.map((m) => (
							<Link key={m.id} href={`/monitors/${m.id}`} className="block">
								<div className="glass-card !p-4 transition hover:border-sky-500/40 dark:hover:border-sky-500/25">
									<div className="flex items-start justify-between gap-2">
										<div className="flex items-center gap-2.5 min-w-0">
											<BrandLogo brand={m.brand} name={m.name} domain={m.url} size={24} />
											<p className="truncate font-medium text-slate-900 dark:text-slate-100">
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
							</Link>
						))}
					</div>
				</>
			)}
		</div>
	);
}
