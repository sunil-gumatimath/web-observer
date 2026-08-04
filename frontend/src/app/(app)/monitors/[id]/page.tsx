"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  ModeBadge,
  PageHeader,
  SectionTitle,
  Spinner,
} from "@/components/ui";
import { ReadableContent } from "@/components/readable-content";
import { ScreenshotImage, ScreenshotLightbox, type ScreenshotMeta } from "@/components/screenshot";
import { api, ApiError } from "@/lib/api";
import type { ChangeEvent, Monitor, MonitorRun, ScreenshotItem } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const POLL_MS = 1500;
const POLL_SLOW_MS = 15_000;
const POLL_MAX_MS = 45_000;

function isActiveRun(r: MonitorRun) {
  return r.status === "queued" || r.status === "running";
}

function screenshotMeta(s: ScreenshotItem | undefined): ScreenshotMeta {
  const meta: ScreenshotMeta = [];
  if (!s) return meta;
  meta.push({ label: "Captured", value: new Date(s.captured_at).toLocaleString() });
  if (s.run_status) meta.push({ label: "Run status", value: s.run_status });
  if (s.distance_from_previous != null) {
    meta.push({ label: "Visual distance", value: `${s.distance_from_previous} (ahash)` });
  } else if (s.is_first) {
    meta.push({ label: "Visual distance", value: "baseline" });
  }
  if (s.ahash) {
    meta.push({
      label: "aHash",
      value: <span className="break-all font-mono text-xs">{s.ahash}</span>,
    });
  }
  if (s.byte_size != null) {
    meta.push({ label: "Size", value: `${(s.byte_size / 1024).toFixed(1)} KB` });
  }
  if (s.content_type) meta.push({ label: "Type", value: s.content_type });
  return meta;
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
  usePageTitle("Monitor detail");
  const router = useRouter();
  const searchParams = useSearchParams();
  const monitorId = params.id;
  const isFresh = searchParams.get("fresh") === "1";

  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [runs, setRuns] = useState<MonitorRun[]>([]);
  const [changes, setChanges] = useState<ChangeEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [pollSlow, setPollSlow] = useState(false);
  const [pollTimedOut, setPollTimedOut] = useState(false);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [showFreshBanner, setShowFreshBanner] = useState(isFresh);

  const [screenshots, setScreenshots] = useState<ScreenshotItem[]>([]);
  const [screenshotsLoading, setScreenshotsLoading] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

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
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load monitor");
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
    showFreshBanner && (runs.length === 0 || runs.every((r) => !TERMINAL.has(r.status)));
  const shouldPoll = !loading && !!workspaceId && (hasActiveRun || waitingForFirst);

  useEffect(() => {
    if (loading || !workspaceId) return;

    if (!shouldPoll) {
      setPolling(false);
      setPollSlow(false);
      pollStartedAt.current = null;
      return;
    }

    setPolling(true);
    setPollTimedOut(false);
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
          setPolling(false);
          setPollSlow(false);
          setPollTimedOut(false);
          pollStartedAt.current = null;
          if (isFreshRef.current) {
            router.replace(`/monitors/${monitorIdRef.current}`, { scroll: false });
          }
        } else if (timedOut) {
          setPolling(false);
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
    const latestOk = runs.find((r) => r.status === "succeeded" && r.snapshot_id);
    const snapId = latestOk?.snapshot_id ?? null;
    if (!workspaceId || !snapId || snapId === latestSnapshotId.current) {
      if (!snapId) setPreviewText(null);
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

  // Load visual screenshot history for visual monitors.
  useEffect(() => {
    if (loading || !workspaceId || !monitor || monitor.mode !== "visual") return;
    let cancelled = false;
    setScreenshotsLoading(true);
    api
      .listScreenshots(workspaceId, monitor.id)
      .then((s) => {
        if (!cancelled) setScreenshots(s);
      })
      .catch(() => {
        if (!cancelled) setScreenshots([]);
      })
      .finally(() => {
        if (!cancelled) setScreenshotsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loading, workspaceId, monitor]);

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
    if (!confirm("Delete this monitor and all its check history?")) return;
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
    setPolling(true);
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
      setPolling(false);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner />;
  if (!monitor) {
    return <ErrorBox message={error ?? "Monitor not found"} />;
  }

  const latestRun = runs[0] ?? null;
  const latestTerminal = runs.find((r) => TERMINAL.has(r.status)) ?? null;
  // Full result panel: after create (?fresh=1), or while any check is in flight.
  const showResultCard =
    showFreshBanner || polling || Boolean(latestRun && isActiveRun(latestRun));

  return (
    <div>
      <PageHeader
        title={monitor.name}
        description={
          <span className="block break-all">{monitor.url}</span>
        }
        actions={
          <>
            <Link href={`/monitors/${monitor.id}/edit`}>
              <Button type="button" variant="secondary">
                Edit
              </Button>
            </Link>
            <Button
              disabled={busy || polling}
              onClick={() =>
                withAction(async () => {
                  try {
                    await api.runMonitor(workspaceId!, monitor.id);
                  } catch (e) {
                    // Already-active run: just continue polling.
                    if (!(e instanceof ApiError && e.status === 409)) throw e;
                  }
                })
              }
            >
              Run now
            </Button>
            {monitor.enabled ? (
              <Button
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
            <Button variant="danger" disabled={busy} onClick={handleDelete}>
              Delete
            </Button>
          </>
        }
      />
      {error ? <ErrorBox message={error} /> : null}

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
                    The job stayed queued/running past {Math.round(POLL_MAX_MS / 1000)}s. Common causes:
                    worker not listening on the right queue, Redis disconnect, or a lost job after restart.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" disabled={busy} onClick={retryCheck}>
                      Retry check
                    </Button>
                    <Button type="button" variant="danger" disabled={busy} onClick={handleDelete}>
                      Delete this monitor
                    </Button>
                  </div>
                </div>
              ) : polling || (latestRun && isActiveRun(latestRun)) || (showFreshBanner && !latestTerminal) ? (
                <div className="mt-3 flex items-center gap-3">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {latestRun?.status === "running" ? "Fetching page…" : "Waiting for worker…"}
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
                    First success sets the baseline without an alert. Future checks will notify you
                    only when content changes.
                  </p>
                  <div className="flex flex-wrap gap-3 text-xs text-slate-500 dark:text-slate-400">
                    {latestTerminal.http_status != null ? (
                      <span>HTTP {latestTerminal.http_status}</span>
                    ) : null}
                    {latestTerminal.latency_ms != null ? (
                      <span>{latestTerminal.latency_ms} ms</span>
                    ) : null}
                    {latestTerminal.finished_at ? (
                      <span>{new Date(latestTerminal.finished_at).toLocaleString()}</span>
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
                    {latestTerminal.error_message || "The first check did not complete successfully."}
                  </p>
                </div>
              ) : (
                <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                  No finished run yet. If this stays empty, ensure the worker is running, then click
                  Run now.
                </p>
              )}
            </div>
            {showFreshBanner && latestTerminal ? (
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  onClick={() => {
                    setShowFreshBanner(false);
                    router.replace(`/monitors/${monitor.id}`, { scroll: false });
                  }}
                >
                  Keep monitoring
                </Button>
                <Button type="button" variant="danger" disabled={busy} onClick={handleDelete}>
                  Delete this monitor
                </Button>
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
                <p className="text-sm text-slate-500">Loading captured content…</p>
              ) : previewText != null && previewText.length > 0 ? (
                <ReadableContent
                  title="What we captured"
                  text={previewText}
                  maxChars={2500}
                  emptyLabel="No text content in this snapshot."
                />
              ) : (
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  No text preview available for this snapshot
                  {monitor.mode === "visual" ? " (visual mode stores image hashes)." : "."}
                </p>
              )}
            </div>
          ) : null}
        </Card>
      ) : null}

      {/* Always available readable snapshot (not only right after create) */}
      {!showResultCard && latestTerminal?.status === "succeeded" ? (
        <section className="mb-8">
          <SectionTitle>Latest captured content</SectionTitle>
          {previewLoading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : previewText != null && previewText.length > 0 ? (
            <ReadableContent text={previewText} maxChars={2500} />
          ) : (
            <Card>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No text preview for the latest successful run
                {monitor.mode === "visual" ? " (visual mode stores image hashes)." : "."}
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

      {monitor.mode === "visual" ? (
        <section className="mb-10">
          <SectionTitle>Screenshot history</SectionTitle>
          {screenshotsLoading ? (
            <Spinner />
          ) : screenshots.length === 0 ? (
            <Card>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No screenshots yet. Run the monitor to capture the first visual snapshot.
              </p>
            </Card>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {screenshots.map((s, i) => (
                <button
                  key={s.snapshot_id}
                  type="button"
                  onClick={() => setLightboxIndex(i)}
                  className="group overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-bg)] text-left transition hover:border-sky-500/40 hover:shadow-glow-sm dark:hover:border-sky-500/25"
                >
                  <div className="relative aspect-video bg-slate-900/30">
                    <ScreenshotImage
                      workspaceId={workspaceId!}
                      snapshotId={s.snapshot_id}
                      alt={`Screenshot captured ${new Date(s.captured_at).toLocaleString()}`}
                      className="h-full w-full"
                      imgClassName="h-full w-full object-cover transition group-hover:scale-[1.03]"
                    />
                    {s.is_first ? (
                      <span className="absolute left-2 top-2 rounded-full bg-slate-900/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                        baseline
                      </span>
                    ) : null}
                  </div>
                  <div className="flex items-center justify-between gap-2 px-3 py-2">
                    <span className="truncate text-[11px] text-slate-500 dark:text-slate-400">
                      {new Date(s.captured_at).toLocaleString()}
                    </span>
                    {s.distance_from_previous != null ? (
                      <Badge tone={s.distance_from_previous > 0 ? "info" : "neutral"}>
                        {s.distance_from_previous} px
                      </Badge>
                    ) : (
                      <span className="text-[11px] text-slate-400">—</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
          <ScreenshotLightbox
            workspaceId={workspaceId!}
            snapshotId={
              lightboxIndex != null ? screenshots[lightboxIndex]?.snapshot_id ?? null : null
            }
            title={
              lightboxIndex != null && screenshots[lightboxIndex]
                ? `Screenshot · ${new Date(screenshots[lightboxIndex].captured_at).toLocaleString()}`
                : "Screenshot"
            }
            meta={lightboxIndex != null ? screenshotMeta(screenshots[lightboxIndex]) : []}
            onClose={() => setLightboxIndex(null)}
            onPrev={
              lightboxIndex != null && lightboxIndex > 0
                ? () => setLightboxIndex(lightboxIndex - 1)
                : undefined
            }
            onNext={
              lightboxIndex != null && lightboxIndex < screenshots.length - 1
                ? () => setLightboxIndex(lightboxIndex + 1)
                : undefined
            }
            hasPrev={lightboxIndex != null && lightboxIndex > 0}
            hasNext={lightboxIndex != null && lightboxIndex < screenshots.length - 1}
          />
        </section>
      ) : null}

      <section className="mb-10">
        <SectionTitle>Recent runs</SectionTitle>
        <div className="surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] bg-slate-50/60 dark:bg-slate-950/40">
                  {["Status", "HTTP", "Latency", "Error", "Finished"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {runs.map((r) => (
                  <tr key={r.id} className="transition hover:bg-slate-100/60 dark:hover:bg-white/[0.02]">
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
                      {r.finished_at ? new Date(r.finished_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
                {runs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center text-slate-500 dark:text-slate-500">
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
                  {c.change_category ? <Badge tone="info">{c.change_category}</Badge> : null}
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
                No change events yet. First success creates a baseline without an alert.
              </p>
            </Card>
          ) : null}
        </div>
      </section>
    </div>
  );
}
