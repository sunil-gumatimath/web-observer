"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
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
import { api } from "@/lib/api";
import type { ChangeEvent, Monitor, MonitorRun } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";

export default function MonitorDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const monitorId = params.id;

  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [runs, setRuns] = useState<MonitorRun[]>([]);
  const [changes, setChanges] = useState<ChangeEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

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

  if (loading) return <Spinner />;
  if (!monitor) {
    return <ErrorBox message={error ?? "Monitor not found"} />;
  }

  return (
    <div>
      <PageHeader
        title={monitor.name}
        description={monitor.url}
        actions={
          <>
            <Link href={`/monitors/${monitor.id}/edit`}>
              <Button type="button" variant="secondary">
                Edit
              </Button>
            </Link>
            <Button
              disabled={busy}
              onClick={() =>
                withAction(async () => {
                  await api.runMonitor(workspaceId!, monitor.id);
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
            <Button
              variant="danger"
              disabled={busy}
              onClick={() =>
                withAction(async () => {
                  if (!confirm("Delete this monitor and its history?")) return;
                  await api.deleteMonitor(workspaceId!, monitor.id);
                  router.push("/monitors");
                })
              }
            >
              Delete
            </Button>
          </>
        }
      />
      {error ? <ErrorBox message={error} /> : null}

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
            <p className="mt-2 truncate font-mono text-xs text-slate-500 dark:text-slate-500">{monitor.css_selector}</p>
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
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-400">{r.http_status ?? "—"}</td>
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
                      No runs yet. Click &quot;Run now&quot;.
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
