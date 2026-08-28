"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
	Badge,
	Button,
	Card,
	CategoryBadge,
	ErrorBox,
	ModeBadge,
	PageHeader,
	SectionTitle,
	Spinner,
} from "@/components/ui";
import { ConfirmButton } from "@/components/confirm-dialog";
import { ReadableContent } from "@/components/readable-content";
import { api, ApiError, brandAssetUrl } from "@/lib/api";
import type { ChangeEvent, Monitor, MonitorRun } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const POLL_MS = 1500;
const POLL_SLOW_MS = 15_000;
const POLL_MAX_MS = 45_000;

function isActiveRun(r: MonitorRun) {
	return r.status === "queued" || r.status === "running";
}

export default function MonitorDetailPage() {
	return (
		<Suspense fallback={<Spinner />}>
			<MonitorDetailInner />
		</Suspense>
	);
}

function MonitorDetailInner() {
	const params = useParams<{ id: string }>();
	const router = useRouter();
	const searchParams = useSearchParams();
	const monitorId = params.id;
	const isFresh = searchParams.get("fresh") === "1";

	const [workspaceId, setWorkspaceId] = useState<string | null>(null);
	const [monitor, setMonitor] = useState<Monitor | null>(null);
	usePageTitle(monitor ? monitor.name : "Monitor detail");
	const [runs, setRuns] = useState<MonitorRun[]>([]);
	const [changes, setChanges] = useState<ChangeEvent[]>([]);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [loading, setLoading] = useState(true);

	const [shareUrl, setShareUrl] = useState<string | null>(null);
	const [shareBusy, setShareBusy] = useState(false);
	const [shareMsg, setShareMsg] = useState<string | null>(null);

	const [pollSlow, setPollSlow] = useState(false);
	const [pollTimedOut, setPollTimedOut] = useState(false);
	const [previewText, setPreviewText] = useState<string | null>(null);
	const [previewLoading, setPreviewLoading] = useState(false);
	const [showFreshBanner, setShowFreshBanner] = useState(isFresh);
	const [brandRefreshing, setBrandRefreshing] = useState(false);
	const [snapshotAiSummary, setSnapshotAiSummary] = useState<string | null>(null);
	const [aiSummarizing, setAiSummarizing] = useState(false);

	const pollStartedAt = useRef<number | null>(null);
	const latestSnapshotId = useRef<string | null>(null);
	// Latest values for the polling interval callback to read without being in
	// the effect deps (prevents the interval from being torn down every poll).
	const isFreshRef = useRef(isFresh);
	const monitorIdRef = useRef(monitorId);
	useEffect(() => {
		isFreshRef.current = isFresh;
		monitorIdRef.current = monitorId;
	}, [isFresh, monitorId]);

	const load = useCallback(async () => {
		const ws = await ensureWorkspace();
		setWorkspaceId(ws);
		const [m, r, c] = await Promise.all([
			api.getMonitor(ws, monitorId),
			api.listRuns(ws, monitorId),
			api.listChanges(ws, monitorId),
		]);
		setMonitor(m);
		setRuns(r);
		setChanges(c);
		return { ws, runs: r };
	}, [monitorId]);

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				await load();
			} catch (e) {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load monitor");
			} finally {
				if (!cancelled) setLoading(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [load]);

	// Poll while a run is active, or when landing with ?fresh=1 until first terminal run.
	//
	// `shouldPoll` is a stable boolean: it stays `true` across successive polls
	// while a run is active, so the effect does NOT re-run (and the interval is
	// NOT torn down/recreated) on every load(). The interval callback reads the
	// latest data via load()'s return value and refs, never via effect deps.
	const hasActiveRun = runs.some(isActiveRun);
	const waitingForFirst =
		showFreshBanner &&
		(runs.length === 0 || runs.every((r) => !TERMINAL.has(r.status)));
	const shouldPoll =
		!loading && !!workspaceId && (hasActiveRun || waitingForFirst);
	const polling = shouldPoll && !pollTimedOut;

	useEffect(() => {
		if (loading || !workspaceId) return;

		if (!shouldPoll) {
			pollStartedAt.current = null;
			return;
		}
		if (pollStartedAt.current == null) pollStartedAt.current = Date.now();

		const id = window.setInterval(async () => {
			try {
				const started = pollStartedAt.current ?? Date.now();
				const elapsed = Date.now() - started;
				if (elapsed > POLL_SLOW_MS) setPollSlow(true);

				const { runs: next } = await load();
				const stillActive = next.some(isActiveRun);
				const hasTerminal = next.some((r) => TERMINAL.has(r.status));
				const timedOut = elapsed > POLL_MAX_MS;

				if (!stillActive && hasTerminal) {
					setPollSlow(false);
					setPollTimedOut(false);
					pollStartedAt.current = null;
					if (isFreshRef.current) {
						router.replace(`/monitors/${monitorIdRef.current}`, {
							scroll: false,
						});
					}
				} else if (timedOut) {
					setPollTimedOut(true);
					pollStartedAt.current = null;
				}
			} catch {
				// keep polling until timeout
			}
		}, POLL_MS);

		return () => window.clearInterval(id);
		// Deps are intentionally stable primitives: the interval is created once per
		// poll session and only recreated when polling starts/stops (shouldPoll),
		// the workspace changes, or initial loading finishes. `load` is stable
		// (useCallback on [monitorId]); `router` is stable in the App Router.
	}, [shouldPoll, loading, workspaceId, load, router]);

	// Load snapshot text preview for latest successful run.
	useEffect(() => {
		const latestOk = runs.find(
			(r) => r.status === "succeeded" && r.snapshot_id,
		);
		const snapId = latestOk?.snapshot_id ?? null;
		if (!workspaceId || !snapId || snapId === latestSnapshotId.current) {
			return;
		}
		latestSnapshotId.current = snapId;
		let cancelled = false;
		setPreviewLoading(true);
		(async () => {
			try {
				const snap = await api.getSnapshot(workspaceId, snapId);
				if (!cancelled) setPreviewText(snap.normalized_text || "");
			} catch {
				if (!cancelled) setPreviewText(null);
			} finally {
				if (!cancelled) setPreviewLoading(false);
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [runs, workspaceId]);

	async function withAction(fn: () => Promise<void>) {
		if (!workspaceId) return;
		setBusy(true);
		setError(null);
		try {
			await fn();
			await load();
		} catch (e) {
			setError(e instanceof Error ? e.message : "Action failed");
		} finally {
			setBusy(false);
		}
	}

	async function handleDelete() {
		if (!workspaceId || !monitor) return;
		setBusy(true);
		setError(null);
		try {
			await api.deleteMonitor(workspaceId, monitor.id);
			router.push("/monitors");
		} catch (e) {
			setError(e instanceof Error ? e.message : "Delete failed");
			setBusy(false);
		}
	}

	async function retryCheck() {
		if (!workspaceId || !monitor) return;
		setBusy(true);
		setError(null);
		setPollTimedOut(false);
		setPollSlow(false);
		pollStartedAt.current = Date.now();
		try {
			try {
				await api.runMonitor(workspaceId, monitor.id);
			} catch (e) {
				// Stuck active run: backend may re-queue after 90s; surface other errors.
				if (!(e instanceof ApiError && e.status === 409)) throw e;
			}
			await load();
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to start check");
			pollStartedAt.current = null;
		} finally {
			setBusy(false);
		}
	}

	async function handleShare() {
		if (!workspaceId || !monitor) return;
		setShareBusy(true);
		setShareMsg(null);
		setError(null);
		try {
			const created = await api.createShareLink(workspaceId, monitor.id);
			setShareUrl(`${window.location.origin}${created.url}`);
			setShareMsg("Share link created — anyone with this URL can view changes (shown only once).");
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to create share link");
		} finally {
			setShareBusy(false);
		}
	}

	function copyShare() {
		if (!shareUrl) return;
		navigator.clipboard?.writeText(shareUrl).then(
			() => setShareMsg("Copied to clipboard."),
			() => setShareMsg(shareUrl),
		);
	}

	async function handleRefreshBrand() {
		if (!workspaceId || !monitor) return;
		setBrandRefreshing(true);
		setError(null);
		try {
			const updated = await api.enrichBrand(workspaceId, monitor.id);
			setMonitor(updated);
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to refresh website thumbnail");
		} finally {
			setBrandRefreshing(false);
		}
	}

	async function handleGenerateAiSummary() {
		if (!workspaceId || !latestTerminal?.snapshot_id) return;
		setAiSummarizing(true);
		setError(null);
		try {
			const res = await api.getSnapshotAiSummary(workspaceId, latestTerminal.snapshot_id);
			setSnapshotAiSummary(res.summary);
		} catch (e) {
			setError(e instanceof Error ? e.message : "Failed to generate AI summary");
		} finally {
			setAiSummarizing(false);
		}
	}

	if (loading) return <Spinner />;
	if (!monitor) {
		return <ErrorBox message={error ?? "Monitor not found"} />;
	}

	const latestRun = runs[0] ?? null;
	const latestTerminal = runs.find((r) => TERMINAL.has(r.status)) ?? null;
	const latestChange = changes[0] ?? null;
	const hasSuccessfulSnapshot = runs.some(
		(r) => r.status === "succeeded" && r.snapshot_id,
	);
	// Full result panel: after create (?fresh=1), or while any check is in flight.
	const showResultCard =
		showFreshBanner || polling || Boolean(latestRun && isActiveRun(latestRun));
	const logo = brandAssetUrl(monitor.brand?.logo_path) || monitor.brand?.logo_url;
	const hero = brandAssetUrl(monitor.brand?.hero_path) || monitor.brand?.hero_url;

	return (
		<div>
			{/* Webdog Hero Header Banner */}
			<div className="mb-8 overflow-hidden rounded-2xl border border-[var(--border)] bg-white shadow-sm dark:bg-slate-950/60">
				{/* Top Cover Hero Banner */}
				<div className="relative h-36 bg-slate-100 sm:h-44 dark:bg-slate-900">
					{hero ? (
						<img
							src={hero}
							alt=""
							className="absolute inset-0 size-full object-cover object-top"
						/>
					) : (
						<div className="absolute inset-0 bg-gradient-to-br from-sky-500/15 via-indigo-500/10 to-slate-200/50 dark:from-sky-950/50 dark:via-indigo-950/30 dark:to-slate-900" />
					)}
					<div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-white via-white/50 to-transparent dark:from-slate-950 dark:via-slate-950/50 dark:to-transparent" />
				</div>

				{/* Floating Header Content */}
				<div className="relative px-5 pb-5 sm:px-6 sm:pb-6">
					<div className="-mt-10 flex flex-wrap items-end justify-between gap-4">
						<div className="flex size-18 sm:size-20 items-center justify-center overflow-hidden rounded-2xl border border-[var(--border)] bg-white p-2 shadow-md dark:bg-slate-900">
							{logo ? (
								<img src={logo} alt="" className="size-12 object-contain" />
							) : (
								<span className="font-mono text-2xl font-bold text-sky-600 dark:text-sky-400">
									{monitor.name?.[0]?.toUpperCase() ?? "W"}
								</span>
							)}
						</div>
						<div className="flex flex-wrap items-center gap-2">
							<a
								href={monitor.url}
								target="_blank"
								rel="noreferrer"
								className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-1.5 text-xs font-medium text-[var(--text)] shadow-sm hover:bg-[var(--surface-bg)] transition dark:border-white/10 dark:hover:bg-white/5"
							>
								Visit site ↗
							</a>
							<Link href={`/monitors/${monitor.id}/edit`}>
								<Button type="button" variant="secondary" size="sm">
									Edit
								</Button>
							</Link>
							<Button
								size="sm"
								disabled={busy || polling}
								onClick={() =>
									withAction(async () => {
										try {
											await api.runMonitor(workspaceId!, monitor.id);
										} catch (e) {
											if (!(e instanceof ApiError && e.status === 409)) throw e;
										}
									})
								}
							>
								Run now
							</Button>
							{monitor.enabled ? (
								<Button
									size="sm"
									variant="secondary"
									disabled={busy}
									onClick={() =>
										withAction(async () => {
											await api.pauseMonitor(workspaceId!, monitor.id);
										})
									}
								>
									Pause
								</Button>
							) : (
								<Button
									size="sm"
									variant="secondary"
									disabled={busy}
									onClick={() =>
										withAction(async () => {
											await api.resumeMonitor(workspaceId!, monitor.id);
										})
									}
								>
									Resume
								</Button>
							)}
							<Button
								size="sm"
								variant="secondary"
								disabled={busy || shareBusy}
								onClick={handleShare}
							>
								{shareBusy ? "Creating…" : "Share"}
							</Button>
							<Button
								type="button"
								size="sm"
								variant="ghost"
								disabled={busy || brandRefreshing}
								onClick={handleRefreshBrand}
								title="Refresh website brand and thumbnail preview"
							>
								{brandRefreshing ? "Refreshing…" : "Refresh brand"}
							</Button>
							<ConfirmButton
								variant="danger"
								size="sm"
								busy={busy}
								error={error}
								onConfirm={handleDelete}
								title="Delete this monitor?"
								body="This permanently deletes the monitor and all of its check history and change events."
							>
								Delete
							</ConfirmButton>
						</div>
					</div>

					<div className="mt-3.5 min-w-0">
						<div className="flex flex-wrap items-center gap-2">
							<h1 className="truncate text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
								{monitor.brand?.title || monitor.name}
							</h1>
							<ModeBadge mode={monitor.mode} />
							<Badge tone={monitor.enabled ? "success" : "warn"}>
								{monitor.enabled ? "active" : "paused"}
							</Badge>
						</div>
						<a
							href={monitor.url}
							target="_blank"
							rel="noreferrer"
							className="mt-1 inline-block truncate font-mono text-xs text-slate-500 hover:text-sky-600 dark:text-slate-400 dark:hover:text-sky-400"
						>
							{monitor.url}
						</a>
						{monitor.brand?.description ? (
							<p className="mt-2 max-w-3xl text-xs sm:text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
								{monitor.brand.description}
							</p>
						) : null}
					</div>
				</div>
			</div>

			{error ? <ErrorBox message={error} /> : null}

			{shareUrl ? (
				<Card className="mb-8 border-emerald-500/25 bg-emerald-500/5 dark:bg-emerald-500/[0.06]">
					<div className="flex flex-wrap items-start justify-between gap-3">
						<div className="min-w-0 flex-1">
							<p className="section-label">Public share link</p>
							<a
								href={shareUrl}
								target="_blank"
								rel="noreferrer"
								className="mt-1 block truncate text-sm text-sky-600 hover:underline dark:text-sky-400"
							>
								{shareUrl}
							</a>
						</div>
						<Button type="button" size="sm" variant="secondary" onClick={copyShare}>
							Copy
						</Button>
					</div>
					{shareMsg ? (
						<p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{shareMsg}</p>
					) : null}
				</Card>
			) : null}

			{showResultCard ? (
				<Card className="mb-8 border-sky-500/25 bg-sky-500/5 dark:bg-sky-500/[0.06]">
					<div className="flex flex-wrap items-start justify-between gap-3">
						<div>
							<p className="section-label">
								{showFreshBanner ? "First check result" : "Check result"}
							</p>
							{pollTimedOut && !latestTerminal ? (
								<div className="mt-3 space-y-3">
									<div className="flex flex-wrap items-center gap-2">
										<Badge tone="warn">taking too long</Badge>
										<span className="text-sm font-medium text-slate-900 dark:text-slate-100">
											Check is stuck or the worker is offline
										</span>
									</div>
									<p className="text-sm text-slate-600 dark:text-slate-300">
										The job stayed queued/running past{" "}
										{Math.round(POLL_MAX_MS / 1000)}s. Common causes: worker not
										listening on the right queue, Redis disconnect, or a lost
										job after restart.
									</p>
									<div className="flex flex-wrap gap-2">
										<Button type="button" disabled={busy} onClick={retryCheck}>
											Retry check
										</Button>
										<ConfirmButton
											variant="danger"
											busy={busy}
											error={error}
											onConfirm={handleDelete}
											title="Delete this monitor?"
											body="This permanently deletes the monitor and all of its check history and change events."
										>
											Delete this monitor
										</ConfirmButton>
									</div>
								</div>
							) : polling ||
								(latestRun && isActiveRun(latestRun)) ||
								(showFreshBanner && !latestTerminal) ? (
								<div className="mt-3 flex items-center gap-3">
									<div className="h-5 w-5 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
									<div>
										<p className="text-sm font-medium text-slate-900 dark:text-slate-100">
											{latestRun?.status === "running"
												? "Fetching page…"
												: "Waiting for worker…"}
											{latestRun ? ` (${latestRun.status})` : ""}
										</p>
										<p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
											{pollSlow
												? "This is taking longer than usual. If it stays queued, the browser/HTTP worker may be offline."
												: "Fetching the page and building a baseline. This usually takes a few seconds."}
										</p>
										{pollSlow ? (
											<Button
												type="button"
												size="sm"
												variant="secondary"
												className="mt-2"
												disabled={busy}
												onClick={retryCheck}
											>
												Retry now
											</Button>
										) : null}
									</div>
								</div>
							) : latestTerminal?.status === "succeeded" ? (
								<div className="mt-3 space-y-2">
									<div className="flex flex-wrap items-center gap-2">
										<Badge tone="success">succeeded</Badge>
										<span className="text-sm font-medium text-slate-900 dark:text-slate-100">
											Baseline captured
										</span>
									</div>
									<p className="text-sm text-slate-600 dark:text-slate-300">
										First success sets the baseline without an alert. Future
										checks will notify you only when content changes.
									</p>
									<div className="flex flex-wrap gap-3 text-xs text-slate-500 dark:text-slate-400">
										{latestTerminal.http_status != null ? (
											<span>HTTP {latestTerminal.http_status}</span>
										) : null}
										{latestTerminal.latency_ms != null ? (
											<span>{latestTerminal.latency_ms} ms</span>
										) : null}
										{latestTerminal.finished_at ? (
											<span>
												{new Date(latestTerminal.finished_at).toLocaleString()}
											</span>
										) : null}
									</div>
								</div>
							) : latestTerminal?.status === "failed" ? (
								<div className="mt-3 space-y-2">
									<div className="flex flex-wrap items-center gap-2">
										<Badge tone="danger">failed</Badge>
										<span className="text-sm font-medium text-slate-900 dark:text-slate-100">
											{latestTerminal.error_code ?? "Check failed"}
										</span>
									</div>
									<p className="text-sm text-slate-600 dark:text-slate-300">
										{latestTerminal.error_message ||
											"The first check did not complete successfully."}
									</p>
								</div>
							) : (
								<p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
									No finished run yet. If this stays empty, ensure the worker is
									running, then click Run now.
								</p>
							)}
						</div>
						{showFreshBanner && latestTerminal ? (
							<div className="flex flex-wrap gap-2">
								<Button
									type="button"
									onClick={() => {
										setShowFreshBanner(false);
										router.replace(`/monitors/${monitor.id}`, {
											scroll: false,
										});
									}}
								>
									Keep monitoring
								</Button>
								<ConfirmButton
									variant="danger"
									busy={busy}
									error={error}
									onConfirm={handleDelete}
									title="Delete this monitor?"
									body="This permanently deletes the monitor and all of its check history and change events."
								>
									Delete this monitor
								</ConfirmButton>
								{latestTerminal.status === "failed" ? (
									<Link href={`/monitors/${monitor.id}/edit`}>
										<Button type="button" variant="secondary">
											Edit &amp; retry
										</Button>
									</Link>
								) : null}
							</div>
						) : null}
					</div>

					{latestTerminal?.status === "succeeded" ? (
						<div className="mt-4 border-t border-[var(--border)] pt-4">
							{previewLoading ? (
								<p className="text-sm text-slate-500">
									Loading captured content…
								</p>
							) : hasSuccessfulSnapshot &&
								previewText != null &&
								previewText.length > 0 ? (
								<ReadableContent
									title="What we captured"
									text={previewText}
									maxChars={2500}
									emptyLabel="No text content in this snapshot."
									baseUrl={monitor?.url}
									aiChangeSummary={latestChange?.ai_summary}
									changeCategory={latestChange?.change_category}
									isNoise={latestChange?.is_noise}
									onSummarizeAi={handleGenerateAiSummary}
									aiSummarizing={aiSummarizing}
									generatedAiSummary={snapshotAiSummary}
								/>
							) : (
								<p className="text-sm text-slate-500 dark:text-slate-400">
									No text preview available for this snapshot
									{"."}
								</p>
							)}
						</div>
					) : null}
				</Card>
			) : null}

			{/* AI Change Summaries Section (Webdog parity: plain-language summaries of what changed and why it matters) */}
			<section className="mb-8">
				<div className="mb-3 flex flex-wrap items-center justify-between gap-2">
					<div>
						<h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
							<span className="flex size-5 items-center justify-center rounded-md bg-sky-500/10 text-sky-500 dark:bg-sky-500/20">
								✨
							</span>
							AI Change Summaries
						</h2>
						<p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
							Plain-language summaries of what changed on this page and why it matters.
						</p>
					</div>
					{latestChange ? (
						<Link
							href={`/changes/${latestChange.id}`}
							className="inline-flex items-center gap-1 text-xs font-medium text-sky-600 hover:text-sky-700 dark:text-sky-400 dark:hover:text-sky-300"
						>
							View full diff &amp; history →
						</Link>
					) : null}
				</div>

				{latestChange ? (
					<div className="overflow-hidden rounded-2xl border border-sky-500/20 bg-gradient-to-br from-sky-50/70 via-white to-indigo-50/30 p-5 shadow-sm dark:border-sky-500/30 dark:from-sky-950/30 dark:via-slate-950 dark:to-indigo-950/20">
						<div className="flex flex-wrap items-center justify-between gap-2 border-b border-sky-500/15 pb-3 dark:border-sky-500/25">
							<div className="flex flex-wrap items-center gap-2">
								<CategoryBadge category={latestChange.change_category} />
								{latestChange.is_noise ? (
									<Badge tone="warn">noise filter held</Badge>
								) : (
									<Badge tone="success">detected change</Badge>
								)}
								<span className="text-xs text-slate-500 dark:text-slate-400 font-mono">
									{new Date(latestChange.created_at).toLocaleString()}
								</span>
							</div>
							<Link
								href={`/changes/${latestChange.id}`}
								className="rounded-lg border border-[var(--border)] bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-xs hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-white/5"
							>
								Inspect Diff
							</Link>
						</div>

						<div className="mt-3.5">
							<p className="text-sm font-medium leading-relaxed text-slate-900 dark:text-slate-100">
								{latestChange.ai_summary || latestChange.diff_summary || "Page content changed."}
							</p>
							{latestChange.diff_summary && latestChange.ai_summary ? (
								<p className="mt-2 text-xs font-mono text-slate-600 dark:text-slate-400">
									{latestChange.diff_summary}
								</p>
							) : null}
						</div>
					</div>
				) : (
					<div className="rounded-2xl border border-[var(--border)] bg-slate-50/60 p-5 shadow-sm dark:bg-slate-900/40">
						<div className="flex items-start gap-3">
							<div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-sky-500/10 text-sky-500 dark:bg-sky-500/20">
								✨
							</div>
							<div className="min-w-0 flex-1">
								<h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
									AI Change Monitoring Active
								</h3>
								<p className="mt-1 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
									Baseline snapshot is established. When future checks detect updates, an AI summary explaining <strong className="text-slate-800 dark:text-slate-200">what changed and why it matters</strong> will be automatically generated and displayed here.
								</p>
								<div className="mt-3 flex flex-wrap items-center gap-2">
									<Badge tone="neutral">Mode: {monitor.mode}</Badge>
									<span className="text-[11px] text-slate-500">
										Checked every {monitor.schedule_interval_minutes}m
									</span>
								</div>
							</div>
						</div>
					</div>
				)}
			</section>

			{/* Always available readable snapshot (not only right after create) */}
			{!showResultCard && latestTerminal?.status === "succeeded" ? (
				<section className="mb-8">
					<SectionTitle>Latest captured content</SectionTitle>
					{previewLoading ? (
						<p className="text-sm text-slate-500">Loading…</p>
					) : hasSuccessfulSnapshot &&
						previewText != null &&
						previewText.length > 0 ? (
						<ReadableContent
							text={previewText}
							maxChars={2500}
							baseUrl={monitor?.url}
							aiChangeSummary={latestChange?.ai_summary}
							changeCategory={latestChange?.change_category}
							isNoise={latestChange?.is_noise}
							onSummarizeAi={handleGenerateAiSummary}
							aiSummarizing={aiSummarizing}
							generatedAiSummary={snapshotAiSummary}
						/>
					) : (
						<Card>
							<p className="text-sm text-slate-500 dark:text-slate-400">
								No text preview for the latest successful run
								{"."}
							</p>
						</Card>
					)}
				</section>
			) : null}

			<div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
				<Card className="!p-4">
					<p className="section-label">Status</p>
					<div className="mt-2.5">
						<Badge tone={monitor.enabled ? "success" : "warn"}>
							{monitor.enabled ? "active" : "paused"}
						</Badge>
					</div>
				</Card>
				<Card className="!p-4">
					<p className="section-label">Mode</p>
					<div className="mt-2.5">
						<ModeBadge mode={monitor.mode} />
					</div>
					{monitor.css_selector ? (
						<p className="mt-2 truncate font-mono text-xs text-slate-500 dark:text-slate-500">
							{monitor.css_selector}
						</p>
					) : null}
				</Card>
				<Card className="!p-4">
					<p className="section-label">Renderer</p>
					<p className="mt-2.5 text-sm font-medium text-slate-900 dark:text-slate-100">
						{monitor.js_required ? "Playwright (JS)" : "HTTP"}
					</p>
				</Card>
				<Card className="!p-4">
					<p className="section-label">Schedule</p>
					<p className="mt-2.5 text-sm font-medium text-slate-900 dark:text-slate-100">
						Every {monitor.schedule_interval_minutes} min
					</p>
				</Card>
				<Card className="!p-4">
					<p className="section-label">Failures in a row</p>
					<p className="mt-2.5 text-sm font-medium text-slate-900 dark:text-slate-100">
						{monitor.consecutive_failures ?? 0}
					</p>
				</Card>
			</div>

			<section className="mb-10">
				<SectionTitle>Recent runs</SectionTitle>
				<div className="surface overflow-hidden">
					<div className="overflow-x-auto">
						<table className="w-full text-left text-sm">
							<thead>
								<tr className="border-b border-[var(--border)] bg-slate-50/60 dark:bg-slate-950/40">
									{["Status", "HTTP", "Latency", "Error", "Finished"].map(
										(h) => (
											<th
												key={h}
												className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-500"
											>
												{h}
											</th>
										),
									)}
								</tr>
							</thead>
							<tbody className="divide-y divide-[var(--border)]">
								{runs.map((r) => (
									<tr
										key={r.id}
										className="transition hover:bg-slate-100/60 dark:hover:bg-white/[0.02]"
									>
										<td className="px-4 py-3">
											<Badge
												tone={
													r.status === "succeeded"
														? "success"
														: r.status === "failed"
															? "danger"
															: "neutral"
												}
											>
												{r.status}
											</Badge>
										</td>
										<td className="px-4 py-3 text-slate-600 dark:text-slate-400">
											{r.http_status ?? "—"}
										</td>
										<td className="px-4 py-3 text-slate-600 dark:text-slate-400">
											{r.latency_ms != null ? `${r.latency_ms}ms` : "—"}
										</td>
										<td className="max-w-xs truncate px-4 py-3 text-slate-600 dark:text-slate-400">
											{r.error_code ?? "—"}
										</td>
										<td className="px-4 py-3 text-slate-500 dark:text-slate-500">
											{r.finished_at
												? new Date(r.finished_at).toLocaleString()
												: "—"}
										</td>
									</tr>
								))}
								{runs.length === 0 ? (
									<tr>
										<td
											colSpan={5}
											className="px-4 py-10 text-center text-slate-500 dark:text-slate-500"
										>
											{polling
												? "First check is running…"
												: 'No runs yet. Click "Run now".'}
										</td>
									</tr>
								) : null}
							</tbody>
						</table>
					</div>
				</div>
			</section>

			<section>
				<SectionTitle>Changes</SectionTitle>
				<div className="space-y-2">
					{changes.map((c) => (
						<Link key={c.id} href={`/changes/${c.id}`} className="block">
							<Card hover className="!py-4">
								<div className="flex flex-wrap items-center gap-2">
									<CategoryBadge category={c.change_category} />
									{c.is_noise ? <Badge tone="warn">noise</Badge> : null}
								</div>
								<p className="mt-2 text-sm text-slate-800 dark:text-slate-200">
									{c.ai_summary || c.diff_summary || "Content changed"}
								</p>
								<p className="mt-1.5 text-xs text-slate-500 dark:text-slate-500">
									{new Date(c.created_at).toLocaleString()}
								</p>
							</Card>
						</Link>
					))}
					{changes.length === 0 ? (
						<Card>
							<p className="text-sm text-slate-500 dark:text-slate-500">
								No change events yet. First success creates a baseline without
								an alert.
							</p>
						</Card>
					) : null}
				</div>
			</section>
		</div>
	);
}
