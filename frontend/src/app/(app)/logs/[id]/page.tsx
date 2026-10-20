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
import { GithubDiff } from "@/components/github-diff";
import { api } from "@/lib/api";
import type { ChangeEventDetail, Monitor, MonitorRunLog } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

function fmt(value: string | null | undefined): string {
	if (!value) return "—";
	const d = new Date(value);
	return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function statusBadge(status: string) {
	switch (status) {
		case "succeeded":
			return <Badge tone="success">success</Badge>;
		case "failed":
			return <Badge tone="danger">failed</Badge>;
		case "cancelled":
			return <Badge tone="warn">cancelled</Badge>;
		case "skipped":
			return <Badge tone="neutral">skipped</Badge>;
		default:
			return <Badge tone="info">running</Badge>;
	}
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
	return (
		<div className="flex items-baseline justify-between gap-4 py-1.5 text-sm">
			<span className="shrink-0 text-[var(--muted)]">{label}</span>
			<span className="min-w-0 truncate text-right">{children}</span>
		</div>
	);
}

export default function RunLogDetailPage() {
	usePageTitle("Run log");

	const params = useParams<{ id: string }>();
	const [workspaceId, setWorkspaceId] = useState<string | null>(null);
	const [run, setRun] = useState<MonitorRunLog | null>(null);
	const [monitor, setMonitor] = useState<Monitor | null>(null);
	const [change, setChange] = useState<ChangeEventDetail | null>(null);
	const [changeLoading, setChangeLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const ws = await ensureWorkspace();
				const detail = await api.getRunDetail(ws, params.id);
				if (cancelled) return;
				setWorkspaceId(ws);
				setRun(detail);
				if (detail.changed && detail.change_id) {
					setChangeLoading(true);
					api
						.getChange(ws, detail.change_id)
						.then((c) => {
							if (!cancelled) setChange(c);
						})
						.catch(() => {})
						.finally(() => {
							if (!cancelled) setChangeLoading(false);
						});
				}
			} catch (e) {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load run log");
			} finally {
				if (!cancelled) setLoading(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [params.id]);

	// Monitor context (URL link, mode) for the run's monitor.
	useEffect(() => {
		if (!workspaceId || !run) return;
		let cancelled = false;
		api
			.getMonitor(workspaceId, run.monitor_id)
			.then((m) => {
				if (!cancelled) setMonitor(m);
			})
			.catch(() => {});
		return () => {
			cancelled = true;
		};
	}, [workspaceId, run]);

	if (loading) {
		return (
			<div className="flex justify-center py-16">
				<Spinner />
			</div>
		);
	}

	return (
		<div>
			<div className="mb-4">
				<Link
					href="/logs"
					className="text-sm text-[var(--muted)] transition hover:text-[var(--fg)]"
				>
					← Back to logs
				</Link>
			</div>

			{error ? <ErrorBox message={error} /> : null}

			{run ? (
				<>
					<PageHeader
						title={run.monitor_name}
						description={`Check run · ${fmt(run.finished_at ?? run.created_at)}`}
						actions={
							<div className="flex items-center gap-2">
								{statusBadge(run.status)}
								{monitor ? (
									<Link href={`/monitors/${monitor.id}`}>
										<Button type="button" variant="secondary" size="sm">
											Open monitor
										</Button>
									</Link>
								) : null}
							</div>
						}
					/>

					<div className="grid gap-4 lg:grid-cols-2">
						{/* Run facts */}
						<Card>
							<SectionTitle>Check details</SectionTitle>
							<InfoRow label="URL">
								{run.monitor_url ? (
									<a
										href={run.monitor_url}
										target="_blank"
										rel="noopener noreferrer"
										className="text-[var(--primary)] underline"
									>
										{run.monitor_url}
									</a>
								) : (
									"—"
								)}
							</InfoRow>
							<InfoRow label="Status">{statusBadge(run.status)}</InfoRow>
							<InfoRow label="HTTP status">{run.http_status ?? "—"}</InfoRow>
							<InfoRow label="Response time">
								{run.latency_ms != null ? `${run.latency_ms} ms` : "—"}
							</InfoRow>
							<InfoRow label="Content changed">
								{run.changed ? (
									<Badge tone="info">changed</Badge>
								) : (
									<Badge tone="neutral">no change</Badge>
								)}
							</InfoRow>
							<InfoRow label="Attempt">#{run.attempt}</InfoRow>
							<InfoRow label="Config version">v{run.config_version}</InfoRow>
							<InfoRow label="Content hash">
								<span className="font-mono text-xs">
									{run.content_hash ? `${run.content_hash.slice(0, 16)}…` : "—"}
								</span>
							</InfoRow>
						</Card>

						{/* Lifecycle timeline */}
						<Card>
							<SectionTitle>Timeline</SectionTitle>
							<InfoRow label="Scheduled">{fmt(run.scheduled_at)}</InfoRow>
							<InfoRow label="Queued">{fmt(run.queued_at)}</InfoRow>
							<InfoRow label="Started">{fmt(run.started_at)}</InfoRow>
							<InfoRow label="Finished">{fmt(run.finished_at)}</InfoRow>

							<div className="mt-4 text-xs text-[var(--muted)]">
								Run ID{" "}
								<span className="font-mono">{run.id}</span>
							</div>
						</Card>
					</div>

					{/* Failure info */}
					{run.error_code || run.error_message ? (
						<div className="mt-4">
							<ErrorBox
								message={`${run.error_code ?? "error"}: ${run.error_message ?? "The check failed."}`}
							/>
						</div>
					) : null}

					{/* Content diff (when the run produced a change) */}
					{run.changed && run.change_id ? (
						<div className="mt-6">
							<SectionTitle>Content change</SectionTitle>
							{changeLoading ? (
								<div className="flex justify-center py-8">
									<Spinner />
								</div>
							) : change ? (
								<div>
									<div className="mb-3 flex flex-wrap items-center gap-2">
										<CategoryBadge category={change.change_category} />
										<Link
											href={`/changes/${change.id}`}
											className="text-sm text-[var(--primary)] underline"
										>
											Open full change view
										</Link>
									</div>
									{change.ai_summary || change.diff_summary ? (
										<p className="mb-4 text-sm text-[var(--muted)]">
											{change.ai_summary || change.diff_summary}
										</p>
									) : null}
									<GithubDiff
										before={change.previous_text}
										after={change.new_text}
										unifiedDiff={change.diff}
										baseUrl={monitor?.url}
									/>
								</div>
							) : (
								<p className="text-sm text-[var(--muted)]">
									Diff could not be loaded.{" "}
									<Link className="underline" href={`/changes/${run.change_id}`}>
										Try the change page directly.
									</Link>
								</p>
							)}
						</div>
					) : null}
				</>
			) : null}
		</div>
	);
}
