"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { AlertInboxItem, AlertsSummary } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";

type Filter = "all" | "unread" | "noise";

export default function AlertsPage() {
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<AlertInboxItem[]>([]);
  const [summary, setSummary] = useState<AlertsSummary | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (ws: string, f: Filter) => {
    const [items, sum] = await Promise.all([
      api.listAlerts(ws, {
        unread_only: f === "unread",
        include_noise: f === "noise" || f === "all",
        limit: 100,
      }).then((list) =>
        f === "noise" ? list.filter((a) => a.is_noise) : f === "all" ? list.filter((a) => !a.is_noise) : list,
      ),
      api.alertsSummary(ws),
    ]);
    setAlerts(items);
    setSummary(sum);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ws = await ensureWorkspace();
        if (cancelled) return;
        setWorkspaceId(ws);
        await load(ws, filter);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load alerts");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [filter, load]);

  async function markRead(alert: AlertInboxItem, isRead = true) {
    if (!workspaceId) return;
    setBusy(true);
    setError(null);
    try {
      await api.markChangeRead(workspaceId, alert.id, isRead);
      await load(workspaceId, filter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update read state");
    } finally {
      setBusy(false);
    }
  }

  async function markAllRead() {
    if (!workspaceId) return;
    setBusy(true);
    setError(null);
    try {
      const sum = await api.markAllAlertsRead(workspaceId);
      setSummary(sum);
      await load(workspaceId, filter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to mark all read");
    } finally {
      setBusy(false);
    }
  }

  async function toggleNoise(alert: AlertInboxItem) {
    if (!workspaceId) return;
    setBusy(true);
    setError(null);
    try {
      await api.markChangeNoise(workspaceId, alert.id, !alert.is_noise);
      await load(workspaceId, filter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update noise");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Alerts"
        description="Every detected change across your monitors — read, open, or mark as noise."
        actions={
          <Button type="button" variant="secondary" disabled={busy || !summary?.unread} onClick={markAllRead}>
            Mark all read
            {summary && summary.unread > 0 ? ` (${summary.unread})` : ""}
          </Button>
        }
      />
      {error ? <ErrorBox message={error} /> : null}

      <div className="mb-6 flex flex-wrap gap-2">
        {(
          [
            ["all", "Active", summary ? summary.total - summary.noise : null],
            ["unread", "Unread", summary?.unread ?? null],
            ["noise", "Noise", summary?.noise ?? null],
          ] as const
        ).map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={
              filter === key
                ? "rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white"
                : "rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"
            }
          >
            {label}
            {count != null ? ` · ${count}` : ""}
          </button>
        ))}
      </div>

      {alerts.length === 0 ? (
        <EmptyState
          title="No alerts yet"
          body="When a monitor detects a content change, it will appear here."
          action={
            <Link href="/monitors/new">
              <Button type="button">Create a monitor</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-2">
          {alerts.map((a) => (
            <Card
              key={a.id}
              className={
                a.is_read
                  ? "!py-4 opacity-90"
                  : "!py-4 border-sky-500/30 bg-sky-500/[0.04] dark:bg-sky-500/[0.06]"
              }
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {!a.is_read ? <Badge tone="info">unread</Badge> : null}
                    {a.is_noise ? <Badge tone="warn">noise</Badge> : null}
                    {a.change_category ? <Badge tone="neutral">{a.change_category}</Badge> : null}
                    <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {a.monitor_name}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-slate-700 dark:text-slate-200">
                    {a.ai_summary || a.diff_summary || "Content changed"}
                  </p>
                  <p className="mt-1.5 truncate text-xs text-slate-500 dark:text-slate-500">
                    {a.monitor_url} · {new Date(a.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link
                    href={`/changes/${a.id}`}
                    onClick={() => {
                      if (!a.is_read) void markRead(a, true);
                    }}
                  >
                    <Button type="button" size="sm">
                      Open
                    </Button>
                  </Link>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => markRead(a, !a.is_read)}
                  >
                    {a.is_read ? "Mark unread" : "Mark read"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => toggleNoise(a)}
                  >
                    {a.is_noise ? "Unmark noise" : "Noise"}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
