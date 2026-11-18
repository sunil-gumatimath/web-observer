import { afterEach, describe, expect, it, vi } from "vitest";
import { exportFileName, triggerBlobDownload } from "@/lib/download";

describe("exportFileName", () => {
  it("builds a dated filename for each export format", () => {
    const day = new Date("2026-11-18T10:00:00Z");
    expect(exportFileName("monitor-runs", "csv", day)).toBe(
      "web-observer-monitor-runs-2026-11-18.csv",
    );
    expect(exportFileName("monitor-runs", "json", day)).toBe(
      "web-observer-monitor-runs-2026-11-18.json",
    );
  });
});

describe("triggerBlobDownload", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("downloads the blob through a temporary anchor and revokes the object URL", () => {
    vi.useFakeTimers();
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:export");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const click = vi.fn();
    const remove = vi.fn();
    const anchor = {
      href: "",
      download: "",
      style: { display: "" },
      click,
      remove,
    };
    const appendChild = vi.fn();
    vi.stubGlobal("document", {
      createElement: vi.fn(() => anchor),
      body: { appendChild },
    });

    const blob = new Blob(["run_id,status\n"], { type: "text/csv" });
    triggerBlobDownload(blob, "runs.csv");

    expect(create).toHaveBeenCalledWith(blob);
    expect(anchor.href).toBe("blob:export");
    expect(anchor.download).toBe("runs.csv");
    expect(appendChild).toHaveBeenCalledWith(anchor);
    expect(click).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledOnce();
    expect(revoke).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(revoke).toHaveBeenCalledWith("blob:export");
  });
});
