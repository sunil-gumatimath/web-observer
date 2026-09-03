"use client";

import Link from "next/link";
import { useState } from "react";
import type { ReactNode } from "react";
import { Badge, Button, Card } from "@/components/ui";

export const ONBOARDING_DISMISSED_KEY = "wo-onboarding-dismissed";

type StepState = "done" | "current" | "todo";

type Step = {
  key: string;
  title: string;
  body: string;
  href: string;
  cta: string;
  done: boolean;
};

function readDismissed(): boolean {
  try {
    return (
      typeof window !== "undefined" &&
      window.localStorage.getItem(ONBOARDING_DISMISSED_KEY) === "1"
    );
  } catch {
    return false;
  }
}

function stateDot(state: StepState, index: number): ReactNode {
  if (state === "done") {
    return (
      <span
        aria-hidden
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-600 ring-1 ring-emerald-500/30 dark:text-emerald-300"
      >
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </span>
    );
  }
  if (state === "current") {
    return (
      <span
        aria-hidden
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sky-500/15 text-xs font-bold text-sky-700 ring-1 ring-sky-500/40 dark:text-sky-300"
      >
        {index + 1}
      </span>
    );
  }
  return (
    <span
      aria-hidden
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--nav-active-bg)] text-xs font-semibold text-[var(--muted)] ring-1 ring-[var(--border)] dark:bg-white/5"
    >
      {index + 1}
    </span>
  );
}

export function OnboardingChecklist({
  hasMonitor,
  hasBaseline,
  hasChannel,
  firstMonitorId = null,
}: {
  hasMonitor: boolean;
  hasBaseline: boolean;
  hasChannel: boolean;
  firstMonitorId?: string | null;
}) {
  const [dismissed, setDismissed] = useState<boolean>(readDismissed);
  if (dismissed) return null;

  const steps: Step[] = [
    {
      key: "monitor",
      title: "Create your first monitor",
      body: "Track a public URL — page content, site links, or product price.",
      href: "/monitors/new",
      cta: "New monitor",
      done: hasMonitor,
    },
    {
      key: "baseline",
      title: "Capture a baseline (Run now)",
      body: "Run your first check to snapshot the page — future changes compare against it.",
      href: firstMonitorId ? `/monitors/${firstMonitorId}` : "/monitors",
      cta: "Open monitor",
      done: hasBaseline,
    },
    {
      key: "channel",
      title: "Enable an alert channel",
      body: "Add an email address so change alerts actually reach you.",
      href: "/settings",
      cta: "Open settings",
      done: hasChannel,
    },
  ];

  const doneCount = steps.filter((s) => s.done).length;
  const firstOpen = steps.findIndex((s) => !s.done);
  const states: StepState[] = steps.map((s, i) =>
    s.done ? "done" : i === firstOpen ? "current" : "todo",
  );

  function dismiss() {
    try {
      window.localStorage.setItem(ONBOARDING_DISMISSED_KEY, "1");
    } catch {
      // storage unavailable — hide for this session only
    }
    setDismissed(true);
  }

  return (
    <Card className="mb-6 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="section-label">Getting started</p>
          <p className="mt-1 text-sm font-medium text-[var(--text)]">
            {doneCount === steps.length
              ? "You're all set up"
              : `${doneCount} of ${steps.length} complete`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={doneCount === steps.length ? "success" : "info"}>
            {doneCount}/{steps.length}
          </Badge>
          <Button type="button" variant="ghost" size="sm" onClick={dismiss} aria-label="Dismiss getting started checklist">
            Dismiss
          </Button>
        </div>
      </div>

      <div
        className="mt-3 h-1.5 overflow-hidden rounded-full bg-[var(--nav-active-bg)] dark:bg-white/10"
        role="progressbar"
        aria-valuenow={doneCount}
        aria-valuemin={0}
        aria-valuemax={steps.length}
        aria-label="Onboarding progress"
      >
        <div
          className="h-full rounded-full bg-sky-500 transition-all"
          style={{ width: `${(100 * doneCount) / steps.length}%` }}
        />
      </div>

      <ol className="mt-4 space-y-2">
        {steps.map((step, i) => {
          const state = states[i];
          return (
            <li
              key={step.key}
              className={
                state === "current"
                  ? "flex items-center justify-between gap-4 rounded-lg border border-sky-500/30 bg-sky-500/[0.06] px-3 py-2.5 dark:border-sky-500/25"
                  : "flex items-center justify-between gap-4 rounded-lg border border-[var(--border)] px-3 py-2.5"
              }
            >
              <div className="flex min-w-0 items-start gap-3">
                {stateDot(state, i)}
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p
                      className={
                        state === "done"
                          ? "text-sm font-medium text-[var(--muted)] line-through decoration-[var(--border)]"
                          : "text-sm font-medium text-[var(--text)]"
                      }
                    >
                      {step.title}
                    </p>
                    {state === "done" ? (
                      <Badge tone="success">Done</Badge>
                    ) : state === "current" ? (
                      <Badge tone="info">Up next</Badge>
                    ) : (
                      <Badge tone="neutral">Todo</Badge>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">{step.body}</p>
                </div>
              </div>
              {state === "done" ? null : (
                <Link href={step.href} className="shrink-0">
                  <Button
                    type="button"
                    variant={state === "current" ? "primary" : "secondary"}
                    size="sm"
                    tabIndex={-1}
                  >
                    {step.cta} →
                  </Button>
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
