import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  getClerkUserIdMock,
  setClerkUserIdMock,
  removeItemMock,
  getItemMock,
  setItemMock,
  meMock,
  createWorkspaceMock,
} = vi.hoisted(() => ({
  getClerkUserIdMock: vi.fn<() => string | null>(() => null),
  setClerkUserIdMock: vi.fn(),
  removeItemMock: vi.fn(),
  getItemMock: vi.fn<() => string | null>(() => null),
  setItemMock: vi.fn(),
  meMock: vi.fn(),
  createWorkspaceMock: vi.fn(),
}));

vi.mock("@/lib/auth-token", () => ({
  getClerkUserId: getClerkUserIdMock,
  setClerkUserId: setClerkUserIdMock,
}));

vi.mock("@/lib/api", () => ({
  api: {
    me: meMock,
    createWorkspace: createWorkspaceMock,
    getUsage: vi.fn(),
    seed: vi.fn(),
  },
}));

vi.mock("@/lib/config", () => ({
  config: { clerkEnabled: true, devWorkspaceId: "" },
}));

import { ensureWorkspace, invalidateWorkspace } from "@/lib/workspace";
import { readCache } from "@/lib/query-cache";

describe("workspace cache invalidation", () => {
  beforeEach(() => {
    const storage = {
      getItem: getItemMock,
      setItem: setItemMock,
      removeItem: removeItemMock,
    };
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal("window", {
      localStorage: storage,
      addEventListener: vi.fn(),
    });
    getClerkUserIdMock.mockReturnValue(null);
    setClerkUserIdMock.mockClear();
    removeItemMock.mockClear();
    meMock.mockReset();
    createWorkspaceMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("clears the tracked Clerk user id and the stored workspace id", () => {
    invalidateWorkspace();

    expect(setClerkUserIdMock).toHaveBeenCalledWith(null);
    expect(removeItemMock).toHaveBeenCalledWith("web_observer_workspace_id");
  });

  it("re-resolves the workspace for the new user after invalidation", async () => {
    getClerkUserIdMock.mockReturnValue("user-a");
    meMock.mockResolvedValueOnce({
      clerk_user_id: "user-a",
      workspaces: [{ id: "ws-a", name: "A", created_at: "" }],
    });
    await expect(ensureWorkspace()).resolves.toBe("ws-a");

    // Sign-out invalidates the cache and clears the tracked identity.
    getClerkUserIdMock.mockReturnValue(null);
    invalidateWorkspace();

    getClerkUserIdMock.mockReturnValue("user-b");
    meMock.mockResolvedValueOnce({
      clerk_user_id: "user-b",
      workspaces: [{ id: "ws-b", name: "B", created_at: "" }],
    });
    await expect(ensureWorkspace()).resolves.toBe("ws-b");
    expect(meMock).toHaveBeenCalledTimes(2);
  });

  it("ignores stale publication and rejection after invalidateWorkspace()", async () => {
    let rejectOldMe!: (err: Error) => void;
    meMock.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectOldMe = reject;
        }),
    );

    const oldPromise = ensureWorkspace();
    invalidateWorkspace();

    getClerkUserIdMock.mockReturnValue("user-b");
    let resolveNewMe!: (v: unknown) => void;
    meMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveNewMe = resolve;
        }),
    );

    const newPromise = ensureWorkspace();
    // Stale failure must not clear the newer resolution's promise.
    rejectOldMe(new Error("aborted"));
    await expect(oldPromise).rejects.toThrow("aborted");

    // A concurrent caller must still reuse the newer in-flight promise (no extra /me call).
    const concurrentPromise = ensureWorkspace();
    expect(meMock).toHaveBeenCalledTimes(2);

    resolveNewMe({
      clerk_user_id: "user-b",
      workspaces: [{ id: "ws-b", name: "B", created_at: "" }],
    });
    await expect(Promise.all([newPromise, concurrentPromise])).resolves.toEqual(["ws-b", "ws-b"]);
    expect(readCache<string>("activeWorkspaceId")?.data).toBe("ws-b");
  });
});
