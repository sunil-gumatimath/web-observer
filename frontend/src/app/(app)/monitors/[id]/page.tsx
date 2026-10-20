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
	ImpactBadge,
	ModeBadge,
	parseImpact,
	SectionTitle,
	Spinner,
	stripImpact,
} from "@/components/ui";
import { ConfirmButton } from "@/components/confirm-dialog";
import { ReadableContent } from "@/components/readable-content";
import { BrandLogo } from "@/components/brand-logo";
import { SkeletonHero } from "@/components/skeleton";
import { VisualDiff } from "@/components/visual-diff";
import { api, ApiError, brandAssetUrl } from "@/lib/api";
import {
  isActiveRun,
  runsSignature,
  TERMINAL_RUN_STATUSES as TERMINAL,
} from "@/lib/monitor-runs";
import type { ChangeEvent, Monitor, MonitorRun, ValuePoint } from "@/lib/types";
import { ValueChart } from "@/components/value-chart";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

// Polling budget: the first check can legitimately take a while (cold backend,
// large pages, browser queue — backend workers allow 120-180s), so the budget
// only expires after this long with *no observed progress* (no new run and no
// status change). Any progress restarts the clock. After expiry the UI says so
// but keeps a slow background watch: a late finish still settles the card
// without a manual refresh.
const POLL_MS = 1500;
// Idle safety net. With no check in flight we still poll — slowly — so a run
// the *scheduler* starts, or one triggered from another tab, shows up without a
// manual reload.
const IDLE_POLL_MS = 15_000;
const POLL_SLOW_MS = 15_000;
const POLL_MAX_MS = 45_000;
// SSE reconnect backoff, and how long the stream may stay silent before the
// fallback poller stops trusting it. The server heartbeats every 15s, so three
// missed beats means the connection is half-open or proxy-buffered.
const SSE_RETRY_MS = 2_000;
const SSE_RETRY_MAX_MS = 30_000;
const SSE_STALL_MS = 45_000;

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
	const [valuePoints, setValuePoints] = useState<ValuePoint[]>([]);
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
	const [sseConnected, setSseConnected] = useState(false);

	const pollStartedAt = useRef<number | null>(null);
	const latestSnapshotId = useRef<string | null>(null);
	// Fingerprint of the last observed run list: any new run or status change
	// counts as progress and restarts the stall budget (see polling effect).
	const lastRunsSig = useRef<string | null>(null);
	// True once SSE has delivered an event on the current connection; the
	// fallback interval idles while the stream is live. Ref (not state) so the
	// stream connecting doesn't tear down and restart the effect.
	const sseLiveRef = useRef(false);
	// When the stream last produced any frame, heartbeats included. Lets the
	// poller notice a half-open or proxy-buffered connection and take over.
	const lastSseAt = useRef(0);
	// Latest `shouldPoll` for callbacks that must not re-create the stream.
	const shouldPollRef = useRef(false);
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
		if (m.mode === "product_price" || m.mode === "json_field") {
			try {
				const h = await api.getValueHistory(ws, monitorId);
				setValuePoints(h.points);
			} catch {
				// History is a bonus panel — never fail the page for it.
			}
		}
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

	// Live updates: SSE primary with polling fallback.
	// `polling` stays true while waiting (even past the stall budget) so the
	// result card keeps its spinner; `pollTimedOut` only switches the card to
	// the "taking too long" advisory while a slow background watch continues.
	const hasActiveRun = runs.some(isActiveRun);
	const waitingForFirst =
		showFreshBanner &&
		(runs.length === 0 || runs.every((r) => !TERMINAL.has(r.status)));
	const shouldPoll =
		!loading && !!workspaceId && (hasActiveRun || waitingForFirst);
	const polling = shouldPoll;
	// The slow/stalled advisories only mean something while a wait is in
	// flight. Deriving them from `shouldPoll` lets them clear themselves the
	// instant the wait ends, with no setState in an effect body.
	const showPollSlow = pollSlow && polling;
	const showPollTimedOut = pollTimedOut && polling;

	useEffect(() => {
		shouldPollRef.current = shouldPoll;
	}, [shouldPoll]);

	// Any new run or status change restarts the stall budget. Without this a
	// healthy-but-slow first check (cold backend, large page, browser queue)
	// outlives the fixed budget and the UI dead-ends while the worker is still
	// going — recoverable only by a manual refresh.
	const noteProgress = useCallback((next: MonitorRun[]) => {
		const sig = runsSignature(next);
		if (sig === lastRunsSig.current) return;
		lastRunsSig.current = sig;
		pollStartedAt.current = Date.now();
		setPollSlow(false);
		setPollTimedOut(false);
	}, []);

	// One refresh path shared by the SSE stream and the fallback poller.
	const refresh = useCallback(async () => {
		const { runs: next } = await load();
		noteProgress(next);

		const stillActive = next.some(isActiveRun);
		const hasTerminal = next.some((r) => TERMINAL.has(r.status));

		if (!stillActive && hasTerminal) {
			// Settled. Clear the wait budget but KEEP the stream open: a
			// scheduled run can start at any moment and must appear without a
			// reload. This used to abort the connection for good.
			pollStartedAt.current = null;
			lastRunsSig.current = null;
			setPollSlow(false);
			setPollTimedOut(false);
			if (isFreshRef.current) {
				// Guard against concurrent refreshes both firing a replace.
				isFreshRef.current = false;
				router.replace(`/monitors/${monitorIdRef.current}`, { scroll: false });
			}
			return;
		}

		const started = pollStartedAt.current;
		if (shouldPollRef.current && started != null) {
			const waited = Date.now() - started;
			if (waited > POLL_SLOW_MS) setPollSlow(true);
			if (waited > POLL_MAX_MS) setPollTimedOut(true);
		}
	}, [load, noteProgress, router]);

	// Arm/clear the stall budget as waits begin and end. Refs only — the
	// advisory flags are derived from `shouldPoll`, so this effect never calls
	// setState (which would cascade an extra render on every transition).
	useEffect(() => {
		if (!shouldPoll) {
			pollStartedAt.current = null;
			lastRunsSig.current = null;
			return;
		}
		if (pollStartedAt.current == null) pollStartedAt.current = Date.now();
	}, [shouldPoll]);

	// SSE stream. Deliberately NOT gated on `shouldPoll`: that flag is derived
	// from the runs loaded once at mount, so a run the scheduler starts later
	// (or one triggered from another tab) left this page permanently stale
	// until a manual reload. The stream now lives as long as the page is
	// mounted and reconnects with backoff when the server ends it.
	useEffect(() => {
		if (loading || !workspaceId) return;
		const ac = new AbortController();
		let stopped = false;
		let retryTimer: number | null = null;
		let backoff = SSE_RETRY_MS;

		async function connect() {
			if (stopped) return;
			try {
				await api.streamMonitorEvents(
					workspaceId!,
					monitorId,
					(event) => {
						lastSseAt.current = Date.now();
						if (event === "connected") {
							setSseConnected(true);
							return;
						}
						if (event === "ping") return; // heartbeat: liveness only
						if (event === "run" || event === "change") {
							sseLiveRef.current = true;
							backoff = SSE_RETRY_MS; // healthy stream: reset backoff
							void refresh().catch(() => {
								/* next frame or poll tick retries */
							});
						}
						// "done"/"error": the server closed the stream. Fall
						// through and reconnect instead of going dark.
					},
					ac.signal,
				);
			} catch {
				/* aborted or transport error — reconnect logic below */
			}
			if (stopped || ac.signal.aborted) return;

			setSseConnected(false);
			sseLiveRef.current = false;
			retryTimer = window.setTimeout(connect, backoff);
			backoff = Math.min(backoff * 2, SSE_RETRY_MAX_MS);
		}

		sseLiveRef.current = false;
		void connect();

		return () => {
			stopped = true;
			if (retryTimer != null) window.clearTimeout(retryTimer);
			ac.abort();
			sseLiveRef.current = false;
			setSseConnected(false);
		};
	}, [loading, workspaceId, monitorId, refresh]);

	// Fallback poller. Always armed while mounted: fast while a check is in
	// flight, slow when idle, and silent whenever the stream is actually
	// delivering. A stream that has gone quiet for SSE_STALL_MS is treated as
	// dead (half-open TCP, buffering proxy) so polling takes over.
	useEffect(() => {
		if (loading || !workspaceId) return;
		const period = shouldPoll ? POLL_MS : IDLE_POLL_MS;
		const id = window.setInterval(() => {
			const streamTrusted =
				sseLiveRef.current && Date.now() - lastSseAt.current < SSE_STALL_MS;
			if (streamTrusted) return;
			void refresh().catch(() => {
				/* keep polling */
			});
		}, period);
		return () => window.clearInterval(id);
	}, [loading, workspaceId, shouldPoll, refresh]);

	// Load snapshot text preview for latest successful run.
	useEffect(() => {
		const latestOk = runs.find(
			(r) => r.status === "succeeded" && r.snapshot_id,
		);
		const snapId = latestOk?.snapshot_id ?? null;
		if (!snapId) {
			if (latestSnapshotId.current !== null) {
				latestSnapshotId.current = null;
				setPreviewText(null);
				setPreviewLoading(false);
			}
			return;
		}
		if (!workspaceId || snapId === latestSnapshotId.current) {
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
				if (!cancelled) {
					setPreviewText(null);
					latestSnapshotId.current = null;
				}
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

	if (loading) return <SkeletonHero />;
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
	const hero = brandAssetUrl(monitor.brand?.hero_path) || monitor.brand?.hero_url;

	return (
		<div>
			{/* Hero Header Banner */}
			<div className="mb-8 overflow-hidden rounded-xl border border-[var(--hairline)] bg-[var(--surface-1)]">
				{/* Top Cover Hero Banner */}
				<div className="relative h-36 bg-[var(--surface-2)] sm:h-44 border-b border-[var(--hairline)]">
					{hero ? (
						<img
							src={hero}
							alt=""
							className="absolute inset-0 size-full object-cover object-top"
						/>
					) : (
						<div className="absolute inset-0 bg-[var(--surface-2)]" />
					)}
				</div>

				{/* Floating Header Content */}
				<div className="relative px-5 pb-5 sm:px-6 sm:pb-6">
					<div className="-mt-10 flex flex-wrap items-end justify-between gap-4">
						<div className="flex size-18 sm:size-20 items-center justify-center overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] p-1.5">
							<BrandLogo brand={monitor.brand} name={monitor.name} domain={monitor.url} size={64} className="rounded-md border-0" />
						</div>
						<div className="flex flex-wrap items-center gap-2">
							<a
								href={monitor.url}
								target="_blank"
								rel="noreferrer"
								className="inline-flex items-center gap-1 rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-1)] px-3 py-1.5 text-xs font-medium text-[var(--ink)] hover:bg-[var(--surface-2)] hover:border-[var(--hairline-strong)] active:bg-[var(--surface-3)] transition"
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
								disabled={busy}
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
							<h1 className="truncate text-xl sm:text-2xl font-bold tracking-tight text-[var(--fg)]">
								{monitor.brand?.title || monitor.name}
							</h1>
							<ModeBadge mode={monitor.mode} />
							<Badge tone={monitor.enabled ? "success" : "warn"}>
								{monitor.enabled ? "active" : "paused"}
							</Badge>
							{workspaceId ? (
								<img src={api.badgeUrl(workspaceId, monitor.id)} alt="status badge" className="h-5 rounded" loading="lazy" />
							) : null}
							{sseConnected ? <span className="h-2 w-2 rounded-full bg-[var(--semantic-success)] animate-pulse" title="live" /> : null}
						</div>
						<a
							href={monitor.url}
							target="_blank"
							rel="noreferrer"
							className="mt-1 inline-block truncate font-mono text-xs text-[var(--ink-subtle)] hover:text-[var(--primary)]"
						>
							{monitor.url}
						</a>
						{monitor.brand?.description ? (
							<p className="mt-2 max-w-3xl text-xs sm:text-sm text-[var(--ink-muted)] leading-relaxed">
								{monitor.brand.description}
							</p>
						) : null}
					</div>
				</div>
			</div>

			{error ? <ErrorBox message={error} /> : null}

			{shareUrl ? (
				<Card className="mb-8 border-[var(--semantic-success)]/30 bg-[var(--semantic-success)]/5">
					<div className="flex flex-wrap items-start justify-between gap-3">
						<div className="min-w-0 flex-1">
							<p className="section-label">Public share link</p>
							<a
								href={shareUrl}
								target="_blank"
								rel="noreferrer"
								className="mt-1 block truncate text-sm text-[var(--primary)] hover:opacity-80"
							>
								{shareUrl}
							</a>
						</div>
						<Button type="button" size="sm" variant="secondary" onClick={copyShare}>
							Copy
						</Button>
					</div>
					{shareMsg ? (
						<p className="mt-3 text-xs text-[var(--ink-subtle)]">{shareMsg}</p>
					) : null}
				</Card>
			) : null}

			{showResultCard ? (
				<Card className="mb-8 border-[var(--hairline)] bg-[var(--surface-1)]">
					<div className="flex flex-wrap items-start justify-between gap-3">
						<div>
							<p className="section-label">
								{showFreshBanner ? "First check result" : "Check result"}
							</p>
							{showPollTimedOut && !latestTerminal ? (
								<div className="mt-3 space-y-3">
									<div className="flex flex-wrap items-center gap-2">
										<Badge tone="warn">taking too long</Badge>
										<span className="text-sm font-medium text-[var(--fg)]">
											Check is stuck or the worker is offline
										</span>
									</div>
									<p className="text-sm text-[var(--ink-muted)]">
										No status change for{" "}
										{Math.round(POLL_MAX_MS / 1000)}s. Common causes: worker not
										listening on the right queue, Redis disconnect, or a lost
										job after restart. Still watching — if the check finishes,
										this page updates on its own.
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
									<div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
									<div>
										<p className="text-sm font-medium text-[var(--fg)]">
											{latestRun?.status === "running"
												? "Fetching page…"
												: "Waiting for worker…"}
											{latestRun ? ` (${latestRun.status})` : ""}
										</p>
										<p className="mt-0.5 text-xs text-[var(--ink-subtle)]">
											{showPollSlow
												? "This is taking longer than usual. If it stays queued, the browser/HTTP worker may be offline."
												: "Fetching the page and building a baseline. This usually takes a few seconds."}
										</p>
										{showPollSlow ? (
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
										<span className="text-sm font-medium text-[var(--fg)]">
											Baseline captured
										</span>
									</div>
									<p className="text-sm text-[var(--ink-muted)]">
										First success sets the baseline without an alert. Future
										checks will notify you only when content changes.
									</p>
									<div className="flex flex-wrap gap-3 text-xs text-[var(--ink-subtle)]">
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
										<span className="text-sm font-medium text-[var(--fg)]">
											{latestTerminal.error_code ?? "Check failed"}
										</span>
									</div>
									<p className="text-sm text-[var(--ink-muted)]">
										{latestTerminal.error_message ||
											"The first check did not complete successfully."}
									</p>
								</div>
							) : (
								<p className="mt-3 text-sm text-[var(--ink-muted)]">
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

				</Card>
			) : null}

			{/* AI Change Summaries — works on 1st add (baseline) and on every change */}
			<section className="mb-8">
				<div className="mb-3 flex flex-wrap items-center justify-between gap-3">
					<div>
						<h2 className="text-sm font-semibold tracking-tight text-[var(--ink)]">
							AI Change Summaries
						</h2>
						<p className="mt-1 text-xs text-[var(--ink-subtle)]">
							Each change gets a 1–2 sentence summary with category and impact.
						</p>
					</div>
					{latestChange ? (
						<Link
							href={`/changes/${latestChange.id}`}
							className="inline-flex items-center gap-1 text-xs font-medium text-[var(--primary)] hover:opacity-80"
						>
							View full diff &amp; history →
						</Link>
					) : null}
				</div>

				{latestChange ? (() => {
					const rawSummary = stripImpact(latestChange.ai_summary || "");
					const title = latestChange.title || (rawSummary.includes(":") && !rawSummary.startsWith("Content changed") && !rawSummary.toLowerCase().includes("likely") ? rawSummary.split(":", 1)[0].trim() : null);
					const summaryBody = title && rawSummary.startsWith(title + ":") 
						? rawSummary.slice(title.length + 1).trim() 
						: rawSummary || latestChange.diff_summary || "Page content changed.";
					const isHeuristic = !latestChange.title && (rawSummary.toLowerCase().includes("likely") || rawSummary.startsWith("Content changed"));
					const impact = latestChange.impact || parseImpact(latestChange.ai_summary);
					const hasDiffTelemetry = Boolean(latestChange.diff_summary && latestChange.diff_summary !== rawSummary && latestChange.diff_summary !== summaryBody);

					return (
						<div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] p-5">
							<div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--hairline)] pb-3">
								<div className="flex flex-wrap items-center gap-2">
									<span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-[var(--primary)]">
										<svg className="size-3.5" viewBox="0 0 24 24" fill="currentColor">
											<path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z" />
										</svg>
										AI Intelligence
									</span>
									<CategoryBadge category={latestChange.change_category} />
									<ImpactBadge impact={impact} />
									{typeof latestChange.confidence === "number" ? (
										<span className="inline-flex items-center gap-1 rounded-full border border-[var(--hairline)] bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-semibold text-[var(--ink-muted)]">
											✦ {Math.round(latestChange.confidence <= 1 ? latestChange.confidence * 100 : latestChange.confidence)}% confidence
										</span>
									) : null}
									{latestChange.is_noise ? (
										<Badge tone="warn">noise held</Badge>
									) : (
										<Badge tone="success">signal</Badge>
									)}
									{isHeuristic ? (
										<span className="inline-flex items-center gap-1 rounded-full bg-[var(--warning)]/10 px-2 py-0.5 text-[10px] font-medium text-[var(--warning)]">
											Heuristic preview
										</span>
									) : null}
									<span className="text-xs text-[var(--ink-subtle)] font-mono">
										{new Date(latestChange.created_at).toLocaleString()}
									</span>
								</div>
								<Link
									href={`/changes/${latestChange.id}`}
									className="inline-flex items-center gap-1 rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] px-3 py-1 text-xs font-semibold text-[var(--ink)] hover:bg-[var(--surface-2)] hover:border-[var(--hairline-strong)]"
								>
									Inspect Diff →
								</Link>
							</div>

							<div className="mt-3.5">
								{title ? (
									<h3 className="text-base font-semibold text-[var(--ink)]">
										{title}
									</h3>
								) : null}
								<p className={`text-sm leading-relaxed text-[var(--fg)] ${title ? "mt-1.5" : "font-medium"}`}>
									{summaryBody}
								</p>
								{hasDiffTelemetry ? (
									<div className="mt-3 flex items-center gap-2 pt-2.5 border-t border-[var(--hairline)] text-[11px] font-mono text-[var(--ink-subtle)]">
										<span>Diff telemetry:</span>
										<span>{latestChange.diff_summary}</span>
									</div>
								) : null}
							</div>
						</div>
					);
				})() : hasSuccessfulSnapshot && latestTerminal?.status === "succeeded" ? (
					<div className="rounded-lg border border-[var(--semantic-success)]/30 bg-[var(--semantic-success)]/5 p-5">
						<div className="flex items-start gap-3">
							<span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--semantic-success)]/15 text-[var(--semantic-success)]">
								✓
							</span>
							<div className="min-w-0 flex-1">
								<h3 className="text-sm font-semibold text-[var(--fg)]">Monitoring active — waiting for changes</h3>
								<p className="mt-1 text-xs leading-relaxed text-[var(--ink-muted)]">
									Baseline captured {latestTerminal.finished_at ? new Date(latestTerminal.finished_at).toLocaleString() : ""} · Next check {monitor.next_run_at ? new Date(monitor.next_run_at).toLocaleString() : `every ${monitor.schedule_interval_minutes}m`} · <ModeBadge mode={monitor.mode} />
								</p>
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
									When a change is detected you&apos;ll get a titled summary + impact here and in Alerts.
								</p>
							</div>
						</div>
					</div>
				) : polling || (latestRun && isActiveRun(latestRun)) ? (
					<div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] p-5">
						<div className="flex items-center gap-3">
							<div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
							<div>
								<p className="text-sm font-medium text-[var(--fg)]">Capturing baseline…</p>
								<p className="text-xs text-[var(--ink-subtle)]">First success creates the baseline — summaries appear after the first real change.</p>
							</div>
						</div>
					</div>
				) : (
					<div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] p-5">
						<p className="text-sm font-medium text-[var(--fg)]">No baseline yet</p>
						<p className="mt-1 text-xs leading-relaxed text-[var(--ink-muted)]">
							Run a check to capture the baseline. AI summaries are generated for each change after that.
						</p>
						<div className="mt-3 flex flex-wrap items-center gap-2">
							<ModeBadge mode={monitor.mode} />
							<Badge tone="neutral">every {monitor.schedule_interval_minutes}m</Badge>
						</div>
					</div>
				)}
			</section>

		{/* Failing is not changing: an outage banner visually distinct from content changes */}
			{(monitor.consecutive_failures ?? 0) > 0 ? (() => {
				const lastFailed = runs.find((r) => r.status === "failed");
				return (
					<div
						role="alert"
						className="mb-8 rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/5 p-5"
					>
						<div className="flex items-start gap-3">
							<span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--danger)]/15 text-base font-bold text-[var(--danger)]">
								!
							</span>
							<div className="min-w-0 flex-1">
								<h3 className="text-sm font-semibold text-[var(--fg)]">
									Monitor is failing — an outage, not a content change
								</h3>
								<p className="mt-1 text-xs leading-relaxed text-[var(--ink-muted)]">
									Failed {monitor.consecutive_failures} time{(monitor.consecutive_failures ?? 0) === 1 ? "" : "s"} in a row
									{lastFailed?.finished_at ? ` · last failure ${new Date(lastFailed.finished_at).toLocaleString()}` : ""}.
									No change alerts fire while checks fail — a separate failure notice goes to your channels instead.
								</p>
								{lastFailed?.error_code || lastFailed?.error_message ? (
									<p className="mt-1.5 truncate font-mono text-xs text-[var(--danger)]">
										{lastFailed.error_code}
										{lastFailed.error_message ? ` — ${lastFailed.error_message}` : ""}
									</p>
								) : null}
							</div>
						</div>
					</div>
				);
			})() : null}

			{/* Latest captured content — always visible when a successful snapshot exists */}
			{hasSuccessfulSnapshot ? (
				<section className="mb-8">
					<SectionTitle>Latest captured content</SectionTitle>
					{previewText &&
					!monitor.js_required &&
					(previewText.length < 80 ||
						/loading\b|enable javascript|requires javascript|please wait/i.test(previewText)) ? (
						<div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--warning)]/30 bg-[var(--warning)]/10 p-3.5 text-xs text-[var(--ink)]">
							<p className="leading-relaxed">
								<strong>Note:</strong> This website may require client-side JavaScript to render its full content. If text looks incomplete, enable <em>JavaScript rendering (Playwright)</em>.
							</p>
							<Button
								size="sm"
								variant="secondary"
								onClick={() => router.push(`/monitors/${monitor.id}/edit`)}
								className="shrink-0 text-xs"
							>
								Enable JS rendering
							</Button>
						</div>
					) : null}
					{previewLoading ? (
						<p className="text-sm text-[var(--ink-subtle)]">Loading captured content…</p>
					) : previewText != null && previewText.length > 0 ? (
						<ReadableContent
							text={previewText}
							maxChars={25000}
							baseUrl={monitor?.url}
						/>
					) : previewText === "" ? (
						<Card>
							<div className="flex flex-wrap items-center justify-between gap-3">
								<p className="text-sm text-[var(--ink-subtle)]">
									Captured snapshot is empty — page had no extractable text. If this is a Single-Page App (SPA) or client-rendered site, enable JavaScript rendering.
								</p>
								{!monitor.js_required ? (
									<Button
										size="sm"
										variant="secondary"
										onClick={() => router.push(`/monitors/${monitor.id}/edit`)}
										className="shrink-0 text-xs"
									>
										Enable JS rendering
									</Button>
								) : null}
							</div>
						</Card>
					) : (
						<Card>
							<p className="text-sm text-[var(--ink-subtle)]">
								No text preview available yet. Run a check — preview appears after the first successful run.
							</p>
						</Card>
					)}
				</section>
			) : null}

			{monitor.screenshots_enabled ? (
				<section className="mb-8">
					<SectionTitle>Visual diff</SectionTitle>
					{(() => {
						// Screenshots are captured only when a non-noise change is recorded
						// (backend _queue_notifications), keyed by that change's run_id —
						// not by arbitrary successful runs, which usually have no file.
						const shotChanges = changes.filter((c) => !c.is_noise).slice(0, 2);
						const after = shotChanges[0]
							? brandAssetUrl(`screenshots/${monitor.id}/${shotChanges[0].run_id}.png`)
							: null;
						const before = shotChanges[1]
							? brandAssetUrl(`screenshots/${monitor.id}/${shotChanges[1].run_id}.png`)
							: null;
						return (
							<>
								<VisualDiff before={before} after={after} />
								{shotChanges.length < 2 ? (
									<p className="mt-2 text-xs text-[var(--ink-subtle)]">
										{shotChanges.length === 0
											? "Screenshots attach to detected changes — none recorded yet. They appear here after the first two signal changes."
											: "One change captured so far — the comparison appears after the next signal change."}
									</p>
								) : null}
							</>
						);
					})()}
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
						<p className="mt-2 truncate font-mono text-xs text-[var(--ink-subtle)]">
							{monitor.css_selector}
						</p>
					) : null}
				</Card>
				<Card className="!p-4">
					<p className="section-label">Renderer</p>
					<p className="mt-2.5 text-sm font-medium text-[var(--fg)]">
						{monitor.js_required ? "Playwright (JS)" : "HTTP"}
					</p>
				</Card>
				<Card className="!p-4">
					<p className="section-label">Schedule</p>
					<p className="mt-2.5 text-sm font-medium text-[var(--fg)]">
						Every {monitor.schedule_interval_minutes} min
					</p>
				</Card>
				<Card className="!p-4">
					<p className="section-label">Failures in a row</p>
					<p className="mt-2.5 text-sm font-medium text-[var(--fg)]">
						{monitor.consecutive_failures ?? 0}
					</p>
				</Card>
			</div>

			{(monitor.mode === "product_price" || monitor.mode === "json_field") ? (
				<section className="mb-10">
					<SectionTitle>Value history</SectionTitle>
					<Card>
						<ValueChart points={valuePoints} />
					</Card>
				</section>
			) : null}

			<section className="mb-10">
				<SectionTitle>Recent runs</SectionTitle>
				<div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
					<div className="overflow-x-auto">
						<table className="w-full text-left text-sm">
							<thead>
								<tr className="border-b border-[var(--hairline)] bg-[var(--surface-1)]">
									{["Status", "HTTP", "Latency", "Error", "Finished"].map(
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
							<tbody className="divide-y divide-[var(--hairline)]">
								{runs.map((r) => (
									<tr
										key={r.id}
										className="transition hover:bg-[var(--surface-2)]"
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
										<td className="px-4 py-3 text-[var(--ink-muted)]">
											{r.http_status ?? "—"}
										</td>
										<td className="px-4 py-3 text-[var(--ink-muted)]">
											{r.latency_ms != null ? `${r.latency_ms}ms` : "—"}
										</td>
										<td className="max-w-xs truncate px-4 py-3 text-[var(--ink-muted)]">
											{r.error_code ?? "—"}
										</td>
										<td className="px-4 py-3 text-[var(--ink-subtle)]">
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
											className="px-4 py-10 text-center text-[var(--ink-subtle)]"
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
								<p className="mt-2 text-sm text-[var(--fg)]">
									{c.ai_summary || c.diff_summary || "Content changed"}
								</p>
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
									{new Date(c.created_at).toLocaleString()}
								</p>
							</Card>
						</Link>
					))}
					{changes.length === 0 ? (
						<Card>
							<p className="text-sm text-[var(--ink-subtle)]">
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
