// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DiffAiAssistant } from "./diff-ai-assistant";

const mocks = vi.hoisted(() => ({ askChangeAi: vi.fn() }));

vi.mock("@/lib/api", () => ({ api: { askChangeAi: mocks.askChangeAi } }));

describe("DiffAiAssistant", () => {
  afterEach(() => {
    cleanup();
    mocks.askChangeAi.mockReset();
  });

  it("shows a loading state, then renders the answer for a quick prompt", async () => {
    mocks.askChangeAi.mockResolvedValue({ text: "### Result\nPrice rose to $29." });
    render(<DiffAiAssistant workspaceId="ws-1" changeId="ch-2" />);

    fireEvent.click(screen.getByRole("button", { name: /Is there any pricing/ }));

    expect(screen.getByText(/preparing analysis/i)).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Result")).toBeTruthy());
    expect(mocks.askChangeAi).toHaveBeenCalledWith(
      "ws-1",
      "ch-2",
      "Is there any pricing or fee change?",
    );
  });

  it("surfaces a rate-limit error and stops loading", async () => {
    mocks.askChangeAi.mockRejectedValue(new Error("429 Too Many Requests"));
    render(<DiffAiAssistant workspaceId="ws-1" changeId="ch-2" />);

    fireEvent.change(screen.getByPlaceholderText(/Ask anything about this diff/), {
      target: { value: "Summarise this" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Ask AI/ }));

    await waitFor(() =>
      expect(screen.getByText(/Rate limit reached — please wait a minute/)).toBeTruthy(),
    );
    expect(screen.queryByText(/preparing analysis/i)).toBeNull();
  });

  it("caps the question at the backend's 2000-character limit", () => {
    render(<DiffAiAssistant workspaceId="ws-1" changeId="ch-2" />);
    const input = screen.getByPlaceholderText(/Ask anything about this diff/);
    expect(input.getAttribute("maxlength")).toBe("2000");
  });
});
