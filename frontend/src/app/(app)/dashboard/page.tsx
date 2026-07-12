"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  ModeBadge,
  PageHeader,
  SectionTitle,
  Spinner,
  StatCard,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { AlertsSummary, Monitor, Usage } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";

export default function DashboardPage() {
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [alerts, setAlerts] = useState<AlertsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ws = await ensureWorkspace();
        const [m, u, a] = await Promise.all([
          api.listMonitors(ws),
          api.getUsage(ws),
          api.alertsSummary(ws).catch(() => null),
        ]);
        if (!cancelled) {
          setMonitors(m);
          setUsage(u);
          setAlerts(a);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load dashboard");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <Spinner />;

  const active = monitors.filter((m) => m.enabled).length;
  const checksPct =
    usage?.checks_limit && usage.checks_limit > 0
      ? (100 * (usage.checks_count ?? 0)) / usage.checks_limit
      : null;
  const monitorsPct =
    usage?.max_monitors && usage.max_monitors > 0
      ? (100 * monitors.length) / usage.max_monitors
      : null;

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Workspace health, usage for today, and your latest monitors."
        actions={
          <Link href="/monitors/new">
            <Button type="button">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              New monitor
            </Button>
          </Link>
        }
      />
      {error ? <ErrorBox message={error} /> : null}

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Monitors"
          value={monitors.length}
          hint={`${active} active · limit ${usage?.max_monitors ?? "—"}`}
          progress={monitorsPct}
        />
        <Link href="/alerts" className="block">
          <StatCard
            label="Unread alerts"
            value={alerts?.unread ?? 0}
            hint={
              alerts
                ? `${alerts.total} total · ${alerts.noise} noise`
                : "Open inbox"
            }
          />
        </Link>
        <StatCard
          label="Checks today"
          value={usage?.checks_count ?? 0}
          hint={`of ${usage?.checks_limit ?? "—"} allowed`}
          progress={checksPct}
        />
        <StatCard
          label="Notifications today"
          value={usage?.notifications_count ?? 0}
          hint="Change alerts sent"
        />
      </div>

      <SectionTitle
        action={
          monitors.length > 0 ? (
            <Link href="/monitors" className="text-xs font-medium text-sky-600 hover:text-sky-700 dark:text-sky-400 dark:hover:text-sky-300">
              View all →
            </Link>
          ) : null
        }
      >
        Recent monitors
      </SectionTitle>

      {monitors.length === 0 ? (
        <EmptyState
          title="No monitors yet"
          body="Create a monitor for a public URL, CSS section, JSON field, or visual screenshot."
          action={
            <Link href="/monitors/new">
              <Button type="button">Create your first monitor</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-2">
          {monitors.slice(0, 8).map((m) => (
            <Link key={m.id} href={`/monitors/${m.id}`} className="block">
              <Card hover className="flex items-center justify-between gap-4 !py-4">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-200/80 text-sky-600 ring-1 ring-slate-300 dark:bg-slate-800/80 dark:text-sky-400 dark:ring-white/10">
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418"
                      />
                    </svg>
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-900 dark:text-slate-100">{m.name}</p>
                    <p className="truncate text-xs text-slate-500 dark:text-slate-500">{m.url}</p>
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
                  <ModeBadge mode={m.mode} />
                  <Badge tone={m.enabled ? "success" : "warn"}>
                    {m.enabled ? "active" : "paused"}
                  </Badge>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
