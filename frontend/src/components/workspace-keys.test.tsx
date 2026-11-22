// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceKeys } from "./workspace-keys";

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
});
