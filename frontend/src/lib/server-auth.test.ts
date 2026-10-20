import { beforeEach, describe, expect, it, vi } from "vitest";

const { protect, configState } = vi.hoisted(() => ({
  protect: vi.fn(),
  configState: { useClerkAuth: false },
}));

vi.mock("@clerk/nextjs/server", () => ({ auth: { protect } }));
vi.mock("@/lib/config", () => ({ config: configState }));

import { requireSession } from "@/lib/server-auth";

describe("requireSession", () => {
  beforeEach(() => {
    protect.mockReset();
  });

  it("skips Clerk protection in internal-token dev mode", async () => {
    configState.useClerkAuth = false;

    await requireSession();

    expect(protect).not.toHaveBeenCalled();
  });

  it("delegates to auth.protect() when Clerk auth is active", async () => {
    configState.useClerkAuth = true;

    await requireSession();

    expect(protect).toHaveBeenCalledTimes(1);
  });

  it("propagates the redirect signalled by auth.protect()", async () => {
    configState.useClerkAuth = true;
    protect.mockRejectedValue(new Error("NEXT_REDIRECT"));

    await expect(requireSession()).rejects.toThrow("NEXT_REDIRECT");
  });
});
