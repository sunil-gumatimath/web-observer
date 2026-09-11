import { describe, expect, it } from "vitest";
import { isActiveRun, isTerminalRun, runsSignature } from "./monitor-runs";
import type { MonitorRun } from "./types";

function run(id: string, status: string): MonitorRun {
  return {
    id,
    monitor_id: "m1",
    workspace_id: "w1",
    config_version: 1,
    status,
    attempt: 1,
    scheduled_at: "2026-01-01T00:00:00Z",
    queued_at: null,
    started_at: null,
    finished_at: null,
    http_status: null,
    latency_ms: null,
    content_hash: null,
    snapshot_id: null,
    error_code: null,
    error_message: null,
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("monitor run status model", () => {
  it("treats every backend non-terminal state as active", () => {
    // Must cover the full backend RunStatus enum: a run that is neither
    // active nor terminal can never settle the first-check wait.
    for (const status of ["scheduled", "queued", "running"]) {
      expect(isActiveRun(run("r1", status))).toBe(true);
      expect(isTerminalRun(run("r1", status))).toBe(false);
    }
  });

  it("treats every backend terminal state as terminal", () => {
    for (const status of ["succeeded", "failed", "cancelled"]) {
      expect(isTerminalRun(run("r1", status))).toBe(true);
      expect(isActiveRun(run("r1", status))).toBe(false);
    }
  });

  it("partitions all known statuses (no neither-nor state)", () => {
    for (const status of ["scheduled", "queued", "running", "succeeded", "failed", "cancelled"]) {
      const r = run("r1", status);
      expect(isActiveRun(r) || isTerminalRun(r)).toBe(true);
    }
  });
});

describe("runsSignature", () => {
  it("is stable when nothing changed", () => {
    const a = [run("r1", "queued"), run("r2", "succeeded")];
    const b = [run("r1", "queued"), run("r2", "succeeded")];
    expect(runsSignature(a)).toBe(runsSignature(b));
  });

  it("changes on status transitions and new runs", () => {
    const before = runsSignature([run("r1", "queued")]);
    expect(runsSignature([run("r1", "running")])).not.toBe(before);
    expect(runsSignature([run("r1", "queued"), run("r2", "queued")])).not.toBe(before);
  });
});
