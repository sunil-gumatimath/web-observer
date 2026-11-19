import { describe, expect, it } from "vitest";
import {
  ALERTS_MAX_LIMIT,
  alertTabTotal,
  canLoadMoreAlerts,
  nextAlertLimit,
} from "@/lib/alerts-pagination";
import type { AlertsSummary } from "@/lib/types";

const summary: AlertsSummary = { total: 250, unread: 30, noise: 50 };

describe("alertTabTotal", () => {
  it("uses the unfiltered signal total for the signal tab", () => {
    expect(alertTabTotal(summary, "all")).toBe(200);
  });

  it("uses the unfiltered noise and unread totals for those tabs", () => {
    expect(alertTabTotal(summary, "noise")).toBe(50);
    expect(alertTabTotal(summary, "unread")).toBe(30);
  });

  it("returns zero while the summary is loading", () => {
    expect(alertTabTotal(null, "all")).toBe(0);
  });
});

describe("alert pagination control", () => {
  it("shows Load more while the requested limit is below the unfiltered total", () => {
    expect(canLoadMoreAlerts(100, alertTabTotal(summary, "all"))).toBe(true);
    expect(canLoadMoreAlerts(200, 200)).toBe(false);
    expect(canLoadMoreAlerts(100, 90)).toBe(false);
  });

  it("stops at the backend's maximum limit instead of requesting an invalid page", () => {
    expect(ALERTS_MAX_LIMIT).toBe(200);
    expect(nextAlertLimit(100, 250)).toBe(200);
    expect(nextAlertLimit(100, 120)).toBe(120);
    expect(nextAlertLimit(200, 250)).toBe(200);
  });
});
