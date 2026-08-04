"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  PageHeader,
  SectionTitle,
  Spinner,
} from "@/components/ui";
import { BeforeAfterDiff } from "@/components/before-after-diff";
import { ScreenshotImage, ScreenshotLightbox, type ScreenshotMeta } from "@/components/screenshot";
import { api } from "@/lib/api";
import type { ChangeEventDetail, MonitorRun, SnapshotAccess } from "@/lib/types";
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
  const [lightbox, setLightbox] = useState<"prev" | "new" | null>(null);

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
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load change");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  // Load screenshot metadata (timestamps) and run status for the visual comparison.
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
      const updated = await api.markChangeNoise(workspaceId, change.id, !change.is_noise);
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

  const isVisual = change.mode === "visual";
  const visualMatch = isVisual ? /ahash distance=(\d+)/i.exec(change.diff_summary ?? "") : null;
  const visualDistance = visualMatch ? Number(visualMatch[1]) : null;

  return (
    <div>
      <PageHeader
        title="Change detail"
        description={change.ai_summary || change.diff_summary || "Content change"}
        actions={
          <>
            <Button type="button" variant="secondary" disabled={busy} onClick={toggleNoise}>
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

      <div className="mb-5 flex flex-wrap gap-2">
        {change.change_category ? <Badge tone="info">{change.change_category}</Badge> : null}
        {change.is_noise ? <Badge tone="warn">noise</Badge> : <Badge tone="success">signal</Badge>}
      </div>

      {change.ai_summary ? (
        <Card className="mb-4">
          <p className="section-label">AI summary</p>
          <p className="mt-2.5 text-sm leading-relaxed text-slate-800 dark:text-slate-200">{change.ai_summary}</p>
        </Card>
      ) : null}

      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <Card className="!p-4">
          <p className="section-label">Previous hash</p>
          <p className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">
            {change.previous_hash ?? "—"}
          </p>
        </Card>
        <Card className="!p-4">
          <p className="section-label">New hash</p>
          <p className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">{change.new_hash}</p>
        </Card>
      </div>

      {isVisual ? (
        <section className="mb-6">
          <SectionTitle>Visual comparison</SectionTitle>
          <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
            Previous (left) vs current (right) screenshot
            {visualDistance != null ? (
              <>
                {" · "}
                <span className="font-medium text-slate-900 dark:text-slate-100">
                  visual distance {visualDistance}
                </span>
                <span className="text-slate-500 dark:text-slate-400"> (ahash)</span>
              </>
            ) : null}
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            <VisualPane
              label="Previous"
              workspaceId={workspaceId!}
              snapshotId={change.previous_snapshot_id}
              snapshot={prevSnap}
              onOpen={() => setLightbox("prev")}
            />
            <VisualPane
              label="Current"
              workspaceId={workspaceId!}
              snapshotId={change.new_snapshot_id}
              snapshot={newSnap}
              runStatus={run?.status ?? null}
              onOpen={() => setLightbox("new")}
            />
          </div>
          <ScreenshotLightbox
            workspaceId={workspaceId!}
            snapshotId={
              lightbox === "prev"
                ? change.previous_snapshot_id
                : lightbox === "new"
                  ? change.new_snapshot_id
                  : null
            }
            title={lightbox === "prev" ? "Previous screenshot" : "Current screenshot"}
            meta={changeLightboxMeta(lightbox, prevSnap, newSnap, run, visualDistance)}
            onClose={() => setLightbox(null)}
          />
        </section>
      ) : null}

      {!isVisual && (change.previous_text || change.new_text) && (
        <div className="mb-6">
          <SectionTitle>Before / After</SectionTitle>
          <BeforeAfterDiff before={change.previous_text} after={change.new_text} />
        </div>
      )}

      {!isVisual && change.diff ? (
        <>
          <SectionTitle>Line diff</SectionTitle>
          <Card className="!p-0 overflow-hidden">
            <div className="max-h-[min(70vh,32rem)] overflow-auto">
              <pre className="diff m-0 whitespace-pre-wrap break-words p-4 font-mono text-[13px] leading-6">
                <DiffLines diff={change.diff} />
              </pre>
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function DiffLines({ diff }: { diff: string }) {
  return (
    <>
      {diff.split("\n").map((line, i) => {
        const trimmed = line.trimStart();
        if (trimmed.startsWith("+") && !trimmed.startsWith("+++")) {
          return (
            <span key={i} className="add block">
              {line}
            </span>
          );
        }
        if (trimmed.startsWith("-") && !trimmed.startsWith("---")) {
          return (
            <span key={i} className="del block">
              {line}
            </span>
          );
        }
        return (
          <span key={i} className="block">
            {line}
          </span>
        );
      })}
    </>
  );
}

function VisualPane({
  label,
  workspaceId,
  snapshotId,
  snapshot,
  runStatus,
  onOpen,
}: {
  label: string;
  workspaceId: string;
  snapshotId: string | null;
  snapshot: SnapshotAccess | null;
  runStatus?: string | null;
  onOpen: () => void;
}) {
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="section-label">{label}</span>
        <div className="flex flex-wrap items-center gap-2">
          {snapshot ? (
            <span className="text-[11px] text-slate-500 dark:text-slate-400">
              {new Date(snapshot.created_at).toLocaleString()}
            </span>
          ) : null}
          {runStatus ? (
            <Badge tone={runStatus === "succeeded" ? "success" : "neutral"}>{runStatus}</Badge>
          ) : null}
        </div>
      </div>
      <button
        type="button"
        onClick={onOpen}
        disabled={!snapshotId}
        className="group block w-full overflow-hidden rounded-xl border border-[var(--border)] bg-slate-900/30 transition hover:border-sky-500/40 disabled:cursor-default"
      >
        <div className="relative flex aspect-video items-center justify-center">
          {snapshotId ? (
            <ScreenshotImage
              workspaceId={workspaceId}
              snapshotId={snapshotId}
              alt={`${label} screenshot`}
              className="h-full w-full"
              imgClassName="h-full w-full object-contain"
            />
          ) : (
            <span className="px-3 text-center text-xs text-slate-500 dark:text-slate-400">
              No previous screenshot (baseline)
            </span>
          )}
        </div>
      </button>
    </div>
  );
}

function changeLightboxMeta(
  lightbox: "prev" | "new" | null,
  prevSnap: SnapshotAccess | null,
  newSnap: SnapshotAccess | null,
  run: MonitorRun | null,
  visualDistance: number | null,
): ScreenshotMeta {
  const snap = lightbox === "prev" ? prevSnap : newSnap;
  const meta: ScreenshotMeta = [];
  if (snap) {
    meta.push({ label: "Captured", value: new Date(snap.created_at).toLocaleString() });
    if (lightbox === "new" && run?.status) meta.push({ label: "Run status", value: run.status });
    if (snap.byte_size != null) {
      meta.push({ label: "Size", value: `${(snap.byte_size / 1024).toFixed(1)} KB` });
    }
    if (snap.content_type) meta.push({ label: "Type", value: snap.content_type });
  }
  if (lightbox === "new" && visualDistance != null) {
    meta.push({ label: "Visual distance", value: `${visualDistance} (ahash)` });
  }
  return meta;
}
