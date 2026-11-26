// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceKeys } from "./workspace-keys";
import { clearQueryCache, writeCache } from "@/lib/query-cache";
import { cacheKeys } from "@/lib/route-prefetch";

const SERVER_BASE = "https://api.kilo.ai/api/gateway";

const mocks = vi.hoisted(() => ({
  getWorkspaceSettings: vi.fn(),
  getModelCatalog: vi.fn(),
  updateWorkspaceKeys: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: mocks }));

function stubApis() {
  mocks.getWorkspaceSettings.mockResolvedValue({
    as_llm_api_key: false,
    llm_api_base: SERVER_BASE,
    llm_model: "reflection/beam-free",
    as_resend_api_key: false,
    email_from: "alerts@example.com",
  });
  mocks.getModelCatalog.mockResolvedValue({
    providers: [
      {
        id: "kilo",
        label: "Kilo",
        base: SERVER_BASE,
        models: [
          { value: "reflection/beam-free", label: "Beam", note: "", recommended: true },
        ],
      },
    ],
  });
  mocks.updateWorkspaceKeys.mockResolvedValue({});
}

describe("WorkspaceKeys", () => {
  afterEach(() => {
    cleanup();
    clearQueryCache();
    mocks.getWorkspaceSettings.mockReset();
    mocks.getModelCatalog.mockReset();
    mocks.updateWorkspaceKeys.mockReset();
  });

  it("never renders an entered key and sends an explicit base with it", async () => {
    stubApis();
    render(<WorkspaceKeys workspaceId="ws-1" />);
    const keyInput = await screen.findByPlaceholderText("sk-…") as HTMLInputElement;

    expect(keyInput.type).toBe("password");
    fireEvent.change(keyInput, { target: { value: "sk-private-value" } });
    fireEvent.click(screen.getByRole("button", { name: /Save keys/ }));

    await waitFor(() => expect(mocks.updateWorkspaceKeys).toHaveBeenCalled());
    const [workspaceId, body] = mocks.updateWorkspaceKeys.mock.calls[0];
    expect(workspaceId).toBe("ws-1");
    expect(body.llm_api_key).toBe("sk-private-value");
    expect(body.llm_api_base).toBe(SERVER_BASE);
    // The secret is cleared from the input after saving.
    expect((screen.getByPlaceholderText("sk-…") as HTMLInputElement).value).toBe("");
  });

  it("shows a save error when the API rejects the configuration", async () => {
    stubApis();
    mocks.updateWorkspaceKeys.mockRejectedValue(new Error("422 base required"));
    render(<WorkspaceKeys workspaceId="ws-1" />);
    await screen.findByPlaceholderText("sk-…");

    fireEvent.change(screen.getByPlaceholderText("sk-…"), {
      target: { value: "sk-private-value" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save keys/ }));

    await waitFor(() => expect(screen.getByText(/422 base required/)).toBeTruthy());
  });

  it("blocks custom base or model overrides client-side when no LLM API key is set (#65)", async () => {
    stubApis();
    render(<WorkspaceKeys workspaceId="ws-1" />);
    await screen.findByPlaceholderText("sk-…");

    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "__custom__" } });
    const customBaseInput = screen.getByPlaceholderText("https://your-gateway.example.com/v1");
    fireEvent.change(customBaseInput, { target: { value: "https://api.openai.com/v1" } });

    fireEvent.click(screen.getByRole("button", { name: /Save keys/ }));

    await waitFor(() =>
      expect(
        screen.getByText(/Enter a workspace LLM API key to save a custom LLM base URL or model/i),
      ).toBeTruthy(),
    );
    expect(mocks.updateWorkspaceKeys).not.toHaveBeenCalled();
  });

  it("preserves user edits made while mount revalidation is pending", async () => {
    stubApis();
    const nowSpy = vi.spyOn(Date, "now");
    nowSpy.mockReturnValue(1_000);
    writeCache(cacheKeys.workspaceSettings("ws-1"), {
      as_llm_api_key: false,
      llm_api_base: SERVER_BASE,
      llm_model: "reflection/beam-free",
      as_resend_api_key: false,
      email_from: "cached@example.com",
    });
    // Advance beyond maxAgeMs so mount triggers background revalidation.
    nowSpy.mockReturnValue(10_000);

    let resolveFresh!: (v: unknown) => void;
    mocks.getWorkspaceSettings.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFresh = resolve;
        }),
    );

    try {
      render(<WorkspaceKeys workspaceId="ws-1" />);
      const senderInput = screen.getByPlaceholderText("alerts@yourdomain.com") as HTMLInputElement;
      expect(senderInput.value).toBe("cached@example.com");

      fireEvent.change(senderInput, { target: { value: "edited@example.com" } });

      await waitFor(() => expect(mocks.getWorkspaceSettings).toHaveBeenCalledTimes(1));
      resolveFresh({
        as_llm_api_key: false,
        llm_api_base: SERVER_BASE,
        llm_model: "reflection/beam-free",
        as_resend_api_key: false,
        email_from: "server@example.com",
      });

      await waitFor(() => {
        expect((screen.getByPlaceholderText("alerts@yourdomain.com") as HTMLInputElement).value).toBe(
          "edited@example.com",
        );
      });
    } finally {
      nowSpy.mockRestore();
    }
  });
});
