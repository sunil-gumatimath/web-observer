// @vitest-environment jsdom
import { render, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAutoRefresh } from "@/lib/use-auto-refresh";

function Harness({
  onTick,
  intervalMs = 15_000,
  minRefreshGapMs = 3_000,
}: {
  onTick: () => void;
  intervalMs?: number;
  minRefreshGapMs?: number;
}) {
  useAutoRefresh(onTick, intervalMs, minRefreshGapMs);
  return null;
}

describe("useAutoRefresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("coalesces back-to-back visibilitychange and focus events within minRefreshGapMs", () => {
    const onTick = vi.fn();
    render(<Harness onTick={onTick} />);

    // Immediate focus right after mount is skipped.
    window.dispatchEvent(new Event("focus"));
    expect(onTick).toHaveBeenCalledTimes(0);

    // Advance past the stale gap, then fire both visibilitychange and focus together.
    vi.advanceTimersByTime(4_000);
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("focus"));
    expect(onTick).toHaveBeenCalledTimes(1);

    // Another focus after the gap refreshes again.
    vi.advanceTimersByTime(3_500);
    window.dispatchEvent(new Event("focus"));
    expect(onTick).toHaveBeenCalledTimes(2);
  });
});
