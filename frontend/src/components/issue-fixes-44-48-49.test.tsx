// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OnboardingChecklist, ONBOARDING_DISMISSED_KEY } from "./onboarding-checklist";
import { CapturedContentPreview } from "./captured-content-preview";

describe("OnboardingChecklist hydration safety (#44)", () => {
  it("hides after mount when dismissed in localStorage", async () => {
    const store = new Map<string, string>([[ONBOARDING_DISMISSED_KEY, "1"]]);
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
      clear: () => store.clear(),
    });
    const { container } = render(
      <OnboardingChecklist hasMonitor={false} hasBaseline={false} hasChannel={false} />,
    );
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });
});

describe("CapturedContentPreview screenshot error reset (#48)", () => {
  it("renders a new screenshot URL after a previous URL errored", () => {
    const monitor = {
      id: "mon-1",
      name: "Visual",
      mode: "visual",
      css_selector: null,
    } as never;

    const { rerender } = render(
      <CapturedContentPreview
        monitor={monitor}
        snapshot={{ normalized_text: "ahash:abc", raw_download_url: "https://cdn.test/1.png" } as never}
        run={{ id: "run-1" } as never}
        loading={false}
      />,
    );

    const img1 = screen.getByRole("img");
    img1.dispatchEvent(new Event("error"));

    rerender(
      <CapturedContentPreview
        monitor={monitor}
        snapshot={{ normalized_text: "ahash:def", raw_download_url: "https://cdn.test/2.png" } as never}
        run={{ id: "run-2" } as never}
        loading={false}
      />,
    );

    const img2 = screen.getByRole("img");
    expect(img2.getAttribute("src")).toContain("2.png");
  });
});

describe("switchWorkspace (#49)", () => {
  it("updates localStorage and activeWorkspaceId cache together", async () => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
      clear: () => store.clear(),
    });
    const { switchWorkspace, ensureWorkspace } = await import("@/lib/workspace");
    switchWorkspace("ws-new");
    expect(localStorage.getItem("web_observer_workspace_id")).toBe("ws-new");
    await expect(ensureWorkspace()).resolves.toBe("ws-new");
  });
});
