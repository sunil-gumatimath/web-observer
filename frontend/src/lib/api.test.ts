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
