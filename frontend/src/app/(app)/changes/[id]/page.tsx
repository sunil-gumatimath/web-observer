"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
	Badge,
	Button,
	Card,
	CategoryBadge,
	ErrorBox,
	PageHeader,
	SectionTitle,
	Spinner,
} from "@/components/ui";
import { BrandLogo } from "@/components/brand-logo";
import { GithubDiff } from "@/components/github-diff";
import { DiffAiAssistant } from "@/components/diff-ai-assistant";
import { api } from "@/lib/api";
import type {
	ChangeEventDetail,
	Monitor,
	MonitorRun,
	SnapshotAccess,
} from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

export default function ChangeDetailPage() {
	usePageTitle("Change detail");

	const params = useParams<{ id: string }>();
	const [workspaceId, setWorkspaceId] = useState<string | null>(null);
	const [change, setChange] = useState<ChangeEventDetail | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);
	const [busy, setBusy] = useState(false);
	const [prevSnap, setPrevSnap] = useState<SnapshotAccess | null>(null);
	const [newSnap, setNewSnap] = useState<SnapshotAccess | null>(null);
	const [run, setRun] = useState<MonitorRun | null>(null);
	const [monitor, setMonitor] = useState<Monitor | null>(null);
	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const ws = await ensureWorkspace();
				const c = await api.getChange(ws, params.id);
				if (!cancelled) {
					setWorkspaceId(ws);
					setChange(c);
				}
				// Opening a change directly (e.g. from an email link) marks it read.
				if (!c.is_read) {
					api.markChangeRead(ws, c.id, true).catch(() => {});
				}
			} catch (e) {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load change");
			} finally {
				if (!cancelled) setLoading(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [params.id]);

	// Load monitor for baseUrl image resolution.
	useEffect(() => {
		if (!workspaceId || !change) return;
		let cancelled = false;
		api.getMonitor(workspaceId, change.monitor_id)
			.then((m) => { if (!cancelled) setMonitor(m); })
			.catch(() => {});
		return () => { cancelled = true; };
	}, [workspaceId, change]);

	// Load snapshot metadata (timestamps) and run status.
	useEffect(() => {
		if (!workspaceId || !change) return;
		let cancelled = false;
		if (change.previous_snapshot_id) {
			api
				.getSnapshot(workspaceId, change.previous_snapshot_id)
				.then((s) => {
					if (!cancelled) setPrevSnap(s);
				})
				.catch(() => {});
		}
		api
			.getSnapshot(workspaceId, change.new_snapshot_id)
			.then((s) => {
				if (!cancelled) setNewSnap(s);
			})
			.catch(() => {});
		if (change.run_id) {
			api
				.getRun(workspaceId, change.run_id)
				.then((r) => {
					if (!cancelled) setRun(r);
				})
				.catch(() => {});
		}
		return () => {
			cancelled = true;
		};
	}, [workspaceId, change]);

	async function toggleNoise() {
		if (!workspaceId || !change) return;
		setBusy(true);
		setError(null);
		try {
			const updated = await api.markChangeNoise(
				workspaceId,
				change.id,
				!change.is_noise,
			);
			setChange({ ...change, is_noise: updated.is_noise });
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to update noise flag");
		} finally {
			setBusy(false);
		}
	}

	if (loading) return <Spinner />;
	if (error && !change) return <ErrorBox message={error} />;
	if (!change) return <ErrorBox message="Change not found" />;

	return (
		<div>
			{monitor ? (
				<div className="mb-4 flex items-center gap-3">
					<BrandLogo name={monitor.name} domain={monitor.url} brand={monitor.brand} size={36} />
					<div className="min-w-0 flex-1">
						<Link
							href={`/monitors/${monitor.id}`}
							className="text-lg font-bold text-[var(--fg)] hover:text-[var(--accent)]"
						>
							{monitor.name}
						</Link>
						<p className="text-xs text-slate-500 font-mono truncate">{monitor.url}</p>
					</div>
				</div>
			) : null}

			<PageHeader
				title="Change detail"
				description={
					change.ai_summary || change.diff_summary || "Content change"
				}
				actions={
					<>
						<Button
							type="button"
							variant="secondary"
							disabled={busy}
							onClick={toggleNoise}
						>
							{change.is_noise ? "Unmark noise" : "Mark as noise"}
						</Button>
						<Link href={`/monitors/${change.monitor_id}`}>
							<Button type="button" variant="ghost">
								Back to monitor
							</Button>
						</Link>
					</>
				}
			/>
			{error ? <ErrorBox message={error} /> : null}

			<div className="mb-5 flex flex-wrap items-center gap-2">
				<CategoryBadge category={change.change_category} />
				{change.is_noise ? (
					<Badge tone="warn">noise</Badge>
				) : (
					<Badge tone="success">signal</Badge>
				)}
				{change.impact ? (
					<Badge
						tone={
							change.impact === "critical"
								? "danger"
								: change.impact === "high"
								? "warn"
								: change.impact === "medium"
								? "info"
								: "neutral"
						}
					>
						impact: {change.impact}
					</Badge>
				) : null}
				{change.confidence !== undefined && change.confidence !== null ? (
					<span className="inline-flex items-center rounded-full bg-slate-200/80 px-2 py-0.5 text-[11px] font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
						{Math.round(change.confidence * 100)}% confidence
					</span>
				) : null}
			</div>

			{change.ai_summary ? (
				<div className="mb-5 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 dark:border-[var(--accent)]/25">
					<div className="flex items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">
						<div className="flex items-center gap-2">
							<svg className="h-4 w-4 text-[var(--accent)]" viewBox="0 0 24 24" fill="currentColor">
								<path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z"/>
							</svg>
							<span>AI Change Summary</span>
						</div>
						{change.title ? (
							<span className="font-semibold text-[var(--fg)] normal-case tracking-normal">
								{change.title}
							</span>
						) : null}
					</div>
					<p className="mt-2 text-sm leading-relaxed font-medium text-[var(--fg)]">
						{change.ai_summary}
					</p>
				</div>
			) : null}

			<div className="mb-6">
				<DiffAiAssistant
					monitorName={monitor?.name}
					changeTitle={change.title}
					impact={change.impact}
					category={change.change_category}
					diffText={change.diff || change.diff_summary}
				/>
			</div>

			<div className="mb-4 grid gap-3 sm:grid-cols-2">
				<Card className="!p-4">
					<p className="section-label">Previous hash</p>
					<p className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">
						{change.previous_hash ?? "—"}
					</p>
					{prevSnap?.created_at ? (
						<p className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-500">
							Captured {new Date(prevSnap.created_at).toLocaleString()}
						</p>
					) : null}
				</Card>
				<Card className="!p-4">
					<p className="section-label">New hash</p>
					<p className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">
						{change.new_hash}
					</p>
					{newSnap?.created_at ? (
						<p className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-500">
							Captured {new Date(newSnap.created_at).toLocaleString()}
						</p>
					) : null}
				</Card>
			</div>

			{run ? (
				<div className="mb-6 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-500">
					<Badge
						tone={
							run.status === "succeeded"
								? "success"
								: run.status === "failed"
									? "danger"
									: "neutral"
						}
					>
						run {run.status}
					</Badge>
					{run.http_status != null ? <span>HTTP {run.http_status}</span> : null}
					{run.latency_ms != null ? <span>· {run.latency_ms} ms</span> : null}
					{run.finished_at ? (
						<span>· {new Date(run.finished_at).toLocaleString()}</span>
					) : null}
				</div>
			) : null}

			{(change.previous_text || change.new_text) && (
				<div className="mb-6">
					<SectionTitle>Before / After</SectionTitle>
					<GithubDiff
						before={change.previous_text}
						after={change.new_text}
						unifiedDiff={change.diff}
						baseUrl={monitor?.url}
					/>
				</div>
			)}
		</div>
	);
}
