/** Alert inbox pagination: gate "Load more" on an unfiltered total. */

import type { AlertsSummary } from "@/lib/types";

export type AlertFilter = "all" | "unread" | "noise";

export const ALERTS_PAGE_SIZE = 100;
/** Backend `list_alerts` caps `limit` at 200 — never request past it. */
export const ALERTS_MAX_LIMIT = 200;

/**
 * The inbox summary counts are independent of client-side search/monitor/
 * impact/date filters. Using them keeps "Load more" available when those
 * filters hide most of the current page.
 */
export function alertTabTotal(
  summary: AlertsSummary | null,
  filter: AlertFilter,
): number {
  if (!summary) return 0;
  if (filter === "unread") return summary.unread;
  if (filter === "noise") return summary.noise;
  return Math.max(0, summary.total - summary.noise);
}

export function canLoadMoreAlerts(limit: number, total: number): boolean {
  return limit < total && limit < ALERTS_MAX_LIMIT;
}

export function nextAlertLimit(limit: number, total: number): number {
  if (!canLoadMoreAlerts(limit, total)) return limit;
  return Math.min(limit + ALERTS_PAGE_SIZE, total, ALERTS_MAX_LIMIT);
}
