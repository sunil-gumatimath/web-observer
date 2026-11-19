import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth-token", () => ({
  getAuthToken: vi.fn(),
}));

vi.mock("@/lib/config", () => ({
  config: {
    apiBaseUrl: "https://api.example.test",
    internalToken: "test-internal-token",
    useClerkAuth: false,
  },
}));

import { api } from "@/lib/api";

describe("api.askChangeAi", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts the prompt to the authenticated workspace change endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ text: "AI response" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(api.askChangeAi("workspace-1", "change-2", "Explain this")).resolves.toEqual({
      text: "AI response",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/workspaces/workspace-1/changes/change-2/ask-ai",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ prompt: "Explain this" }),
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Token": "test-internal-token",
        },
      }),
    );
  });
});

describe("api authenticated exports", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches run-log export as a blob with auth headers and every filter in the query", async () => {
    const csv = "run_id,status\nrun-1,succeeded\n";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(csv, {
        status: 200,
        headers: { "Content-Type": "text/csv" },
      }),
    );

    const blob = await api.exportRunLogs(
      "workspace-1",
      {
        monitorId: "monitor-1",
        outcome: "failed",
        from: "2026-01-01",
        to: "2026-01-31",
      },
      "json",
    );

    expect(await blob.text()).toBe(csv);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/workspaces/workspace-1/export/runs?format=json&monitor_id=monitor-1&outcome=failed&date_from=2026-01-01&date_to=2026-01-31",
      expect.objectContaining({
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Token": "test-internal-token",
        },
      }),
    );
  });

  it("exports monitors as CSV by default and uses the internal-token header", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("id,name\n1,Monitor\n", { status: 200 }));

    await api.exportMonitors("workspace-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/workspaces/workspace-1/export/monitors?format=csv",
      expect.objectContaining({
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Token": "test-internal-token",
        },
      }),
    );
  });

  it("exports changes with auth headers", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("[]", { status: 200 }));

    await api.exportChanges("workspace-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/workspaces/workspace-1/export/changes",
      expect.objectContaining({
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Token": "test-internal-token",
        },
      }),
    );
  });

  it("turns a non-OK export response into an ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "forbidden" }), { status: 403 }),
    );

    await expect(api.exportMonitors("workspace-1")).rejects.toMatchObject({
      status: 403,
    });
  });
});

describe("api.listAlerts filters", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("propagates unread/noise/limit into the query instead of client-side filtering", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("[]", { status: 200 }));

    await api.listAlerts("workspace-1", {
      unread_only: true,
      include_noise: true,
      limit: 200,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/v1/workspaces/workspace-1/alerts?unread_only=true&include_noise=true&limit=200",
      expect.objectContaining({
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Token": "test-internal-token",
        },
      }),
    );
  });
});
