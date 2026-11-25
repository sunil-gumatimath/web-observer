import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearQueryCache,
  fetchCached,
  invalidateCachePrefix,
  readCache,
  updateCached,
  writeCache,
} from "@/lib/query-cache";

describe("query-cache", () => {
  beforeEach(() => {
    clearQueryCache();
  });

  it("deduplicates concurrent in-flight requests for the same key", async () => {
    let resolveFn!: (v: string) => void;
    const fetcher = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveFn = resolve;
        }),
    );

    const p1 = fetchCached("k1", fetcher);
    const p2 = fetchCached("k1", fetcher);
    expect(fetcher).toHaveBeenCalledTimes(1);

    resolveFn("ok");
    await expect(Promise.all([p1, p2])).resolves.toEqual(["ok", "ok"]);
    expect(readCache<string>("k1")?.data).toBe("ok");
  });

  it("returns fresh cached data without re-fetching when within maxAgeMs", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce("v1").mockResolvedValueOnce("v2");

    await expect(fetchCached("k2", fetcher, { maxAgeMs: 10_000 })).resolves.toBe("v1");
    await expect(fetchCached("k2", fetcher, { maxAgeMs: 10_000 })).resolves.toBe("v1");
    expect(fetcher).toHaveBeenCalledTimes(1);

    await expect(fetchCached("k2", fetcher, { force: true })).resolves.toBe("v2");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("discards stale in-flight responses if clearQueryCache runs mid-request", async () => {
    let resolveOld!: (v: string) => void;
    const oldPromise = fetchCached(
      "ws:me",
      () =>
        new Promise<string>((resolve) => {
          resolveOld = resolve;
        }),
    );

    clearQueryCache();
    resolveOld("user-a-data");
    await expect(oldPromise).resolves.toBe("user-a-data");
    expect(readCache("ws:me")).toBeUndefined();
  });

  it("supports prefix invalidation and optimistic updates", () => {
    writeCache("alerts:ws1:all:100", [1, 2]);
    writeCache("alerts:ws1:unread:100", [1]);
    writeCache("monitors:ws1", ["m1"]);

    updateCached<string[]>("monitors:ws1", (list) => [...list, "m2"]);
    expect(readCache<string[]>("monitors:ws1")?.data).toEqual(["m1", "m2"]);

    invalidateCachePrefix("alerts:ws1:");
    expect(readCache("alerts:ws1:all:100")).toBeUndefined();
    expect(readCache("alerts:ws1:unread:100")).toBeUndefined();
    expect(readCache("monitors:ws1")?.data).toEqual(["m1", "m2"]);
  });
});
