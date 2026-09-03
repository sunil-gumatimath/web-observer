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
  StatCard,
} from "@/components/ui";
import { SkeletonStats, SkeletonCard } from "@/components/skeleton";
import { BrandLogo } from "@/components/brand-logo";
import { ActivityBars, Sparkline } from "@/components/sparkline";
import { OnboardingChecklist } from "@/components/onboarding-checklist";
import { bucketActivity } from "@/lib/activity";
import { api } from "@/lib/api";
import type {
  AlertsSummary,
  Monitor,
  NotificationChannel,
  Usage,
} from "@/lib/types";
import {
  ImpactBadge,
  parseImpact,
  stripImpact,
} from "@/components/ui";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

const CHANGE_COLORS: Record<string, string> = {
  pricing: "bg-emerald-500",
  availability: "bg-sky-500",
  legal: "bg-amber-500",
  content: "bg-violet-500",
  design: "bg-pink-500",
  api: "bg-indigo-500",
  other: "bg-slate-400",
};

function changeDotClass(cat: string | null): string {
  if (!cat) return "bg-slate-300 dark:bg-slate-600";
  return CHANGE_COLORS[cat] ?? "bg-slate-400";
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function DashboardPage() {
  usePageTitle("Overview");
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [alerts, setAlerts] = useState<AlertsSummary | null>(null);
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ws = await ensureWorkspace();
        const [m, u, a, c] = await Promise.all([
          api.listMonitors(ws),
          api.getUsage(ws),
          api.alertsSummary(ws).catch(() => null),
          api.listNotificationChannels(ws).catch(() => []),
        ]);
        if (!cancelled) {
          setMonitors(m);
          setUsage(u);
          setAlerts(a);
          setChannels(c);
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

  if (loading)
    return (
      <div suppressHydrationWarning className="space-y-4">
        <SkeletonStats />
        <div suppressHydrationWarning className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );

  const active = monitors.filter((m) => m.enabled).length;
  // 14-day change activity from latest_change timestamps (no extra API call).
  const activity = bucketActivity(monitors, new Date());
  const checksPct =
    usage?.checks_limit && usage.checks_limit > 0
      ? (100 * (usage.checks_count ?? 0)) / usage.checks_limit
      : null;
  const monitorsPct =
    usage?.max_monitors && usage.max_monitors > 0
      ? (100 * monitors.length) / usage.max_monitors
      : null;
  const hasMonitor = monitors.length > 0;
  const hasBaseline = monitors.some((m) => m.latest_change);
  const hasChannel = channels.some((c) => c.enabled);
  const showChecklist = monitors.length === 0 || !hasBaseline;

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
        <StatCard
          label="Unread alerts"
          value={alerts?.unread ?? 0}
          hint={
            alerts
              ? `${alerts.total} total · ${alerts.noise} noise`
              : "Open inbox"
          }
        />
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

      <Card className="mb-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="section-label">Change activity</p>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {activity.total === 0
                ? "No changes detected in the last 14 days."
                : `${activity.total} change${activity.total === 1 ? "" : "s"} in the last 14 days.`}
            </p>
          </div>
          <Sparkline values={activity.counts} label="Changes per day, last 14 days" />
        </div>
        <div className="mt-4">
          <ActivityBars values={activity.counts} labels={activity.labels} />
          <div className="mt-1.5 flex justify-between text-[10px] text-[var(--muted)]">
            <span>{activity.labels[0]}</span>
            <span>{activity.labels[activity.labels.length - 1]}</span>
          </div>
        </div>
      </Card>

      {showChecklist ? (
        <OnboardingChecklist
          hasMonitor={hasMonitor}
          hasBaseline={hasBaseline}
          hasChannel={hasChannel}
          firstMonitorId={monitors[0]?.id ?? null}
        />
      ) : null}

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
          body="Create a monitor for a public URL — page content, site links, or product price."
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
                <div className="flex min-w-0 items-start gap-3">
                  <BrandLogo brand={m.brand} name={m.name} domain={m.url} size={28} className="mt-0.5" />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-medium text-slate-900 dark:text-slate-100">{m.name}</p>
                      {m.latest_change && !m.latest_change.is_read ? <Badge tone="info">new</Badge> : null}
                      {m.latest_change?.change_category ? (
                        <span className={`h-2 w-2 rounded-full ${changeDotClass(m.latest_change.change_category)}`} aria-hidden />
                      ) : null}
                      {m.latest_change?.ai_summary ? <ImpactBadge impact={parseImpact(m.latest_change.ai_summary)} /> : null}
                    </div>
                    <p className="truncate text-xs text-slate-500 dark:text-slate-500">{m.url}</p>
                    <p className="mt-1 truncate text-sm text-slate-700 dark:text-slate-200">
                      {m.latest_change
                        ? stripImpact(m.latest_change.ai_summary || "") ||
                          m.latest_change.diff_summary ||
                          "Content changed"
                        : "Watching — no changes yet"}
                    </p>
                    {m.latest_change ? (
                      <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
                        {relativeTime(m.latest_change.created_at)}
                        {m.latest_change.is_noise ? " · noise" : ""}
                      </p>
                    ) : null}
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
