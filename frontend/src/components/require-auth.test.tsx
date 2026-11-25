// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const configState = vi.hoisted(() => ({
  devModeEnabled: false,
  clerkEnabled: false,
  useClerkAuth: true,
  devWorkspaceId: "",
  apiBaseUrl: "http://127.0.0.1:8002",
  internalToken: "",
  clerkPublishableKey: "",
  cfBeaconToken: "",
}));

vi.mock("@/lib/config", () => ({
  config: configState,
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => {
    throw new Error("You must wrap your application in a <ClerkProvider> component.");
  },
  UserButton: () => null,
}));

import { RequireAuth } from "./require-auth";

describe("RequireAuth (#31)", () => {
  beforeEach(() => {
    configState.devModeEnabled = false;
    configState.clerkEnabled = false;
  });

  it("renders Sign in required card instead of crashing when prod has no Clerk key", () => {
    render(
      <RequireAuth>
        <div>Secret dashboard</div>
      </RequireAuth>,
    );
    expect(screen.getByText("Sign in required")).toBeTruthy();
    expect(screen.queryByText("Secret dashboard")).toBeNull();
  });

  it("renders children in dev mode without Clerk", () => {
    configState.devModeEnabled = true;
    configState.clerkEnabled = false;
    render(
      <RequireAuth>
        <div>Dev dashboard</div>
      </RequireAuth>,
    );
    expect(screen.getByText("Dev dashboard")).toBeTruthy();
  });
});

describe("Workspace switcher storage order (#22)", () => {
  it("preserves selected workspace id after invalidateWorkspace()", async () => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
      clear: () => store.clear(),
    });
    const { invalidateWorkspace, setStoredWorkspaceId } = await import("@/lib/workspace");
    invalidateWorkspace();
    setStoredWorkspaceId("ws-2");
    expect(localStorage.getItem("web_observer_workspace_id")).toBe("ws-2");
  });
});
