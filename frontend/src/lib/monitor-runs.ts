import type { MonitorRun } from "./types";

/**
 * Run-status model shared by the monitor detail live view.
 *
 * Must stay in sync with the backend `RunStatus` enum
 * (`backend/app/models/entities.py`): scheduled/queued/running are all
 * non-terminal worker states, succeeded/failed/cancelled are terminal.
 * Treating them as a complete partition matters: a run the UI considers
 * "neither active nor terminal" can never settle the first-check wait,
 * which previously left the page spinning until a manual refresh.
 */
export const TERMINAL_RUN_STATUSES: ReadonlySet<string> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);

export function isActiveRun(r: MonitorRun): boolean {
  return r.status === "scheduled" || r.status === "queued" || r.status === "running";
}

export function isTerminalRun(r: MonitorRun): boolean {
  return TERMINAL_RUN_STATUSES.has(r.status);
}

/** Compact fingerprint of the run list; changes iff a run was added or changed status. */
export function runsSignature(runs: MonitorRun[]): string {
  return runs.map((r) => `${r.id}:${r.status}`).join(",");
}
