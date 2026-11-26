// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TeamInvites } from "./team-invites";
import { ThresholdEditor } from "./threshold-editor";

vi.mock("@/lib/api", () => ({
  api: {
    listInvites: vi.fn().mockResolvedValue([]),
    createInvite: vi.fn(),
    revokeInvite: vi.fn(),
  },
}));

describe("TeamInvites role options (#63)", () => {
  it("does not offer owner in the invite role dropdown", async () => {
    render(<TeamInvites workspaceId="ws-1" />);
    const select = screen.getByRole("combobox");
    const values = Array.from(select.querySelectorAll("option")).map(
      (opt) => (opt as HTMLOptionElement).value,
    );
    expect(values).toEqual(["member", "admin", "viewer"]);
    expect(values).not.toContain("owner");
    await waitFor(() => {
      expect(screen.getByText("No invite links yet.")).toBeTruthy();
    });
  });
});

describe("ThresholdEditor flap_max_alerts (#64)", () => {
  it("sets min=1, shows an error for 0 without committing, and commits >= 1", () => {
    const onChange = vi.fn();
    render(<ThresholdEditor mode="page_content" value={null} onChange={onChange} />);

    const input = screen.getByLabelText("Max alerts in flap window") as HTMLInputElement;
    expect(input.min).toBe("1");

    fireEvent.change(input, { target: { value: "0" } });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a valid number (at least 1).")).toBeTruthy();

    fireEvent.change(input, { target: { value: "2" } });
    expect(onChange).toHaveBeenCalledWith({ flap_max_alerts: 2 });
  });
});
