/**
 * Lightweight workspace-scoped client cache with in-flight deduplication and
 * epoch-based invalidation so switching tabs renders cached data immediately
 * while revalidating in the background.
 */

export type CacheEntry<T> = {
  data: T;
  updatedAt: number;
};

const store = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();
let cacheEpoch = 0;

/** Read a cached entry synchronously (returns undefined on miss). */
export function readCache<T>(key: string): CacheEntry<T> | undefined {
  return store.get(key) as CacheEntry<T> | undefined;
}

/** True when an entry exists and is younger than `maxAgeMs`. */
export function isCacheFresh(
  entry: CacheEntry<unknown> | undefined,
  maxAgeMs: number,
): boolean {
  if (!entry || maxAgeMs <= 0) return false;
  return Date.now() - entry.updatedAt < maxAgeMs;
}

/** Write a value to the cache under the current epoch. */
export function writeCache<T>(key: string, data: T): CacheEntry<T> {
  const entry: CacheEntry<T> = { data, updatedAt: Date.now() };
  store.set(key, entry);
  return entry;
}

/** Update an existing cached entry if present. */
export function updateCached<T>(key: string, updater: (prev: T) => T): void {
  const existing = readCache<T>(key);
  if (!existing) return;
  writeCache(key, updater(existing.data));
}

/** Remove all cached entries and drop in-flight tracking for old sessions. */
export function clearQueryCache(): void {
  cacheEpoch += 1;
  store.clear();
  inflight.clear();
}

/** Drop cached entries matching a prefix (e.g. after a mutation). */
export function invalidateCachePrefix(prefix: string): void {
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) store.delete(key);
  }
}

/**
 * Fetch and cache a resource with in-flight request deduplication.
 *
 * - When `maxAgeMs > 0` and `force` is false, a fresh entry is returned
 *   without issuing a network request.
 * - Concurrent callers for the same `key` share one in-flight promise.
 * - If `clearQueryCache()` runs while a request is in flight, the stale
 *   response is discarded instead of poisoning the next user/workspace.
 */
export function fetchCached<T>(
  key: string,
  fetcher: () => Promise<T>,
  options?: { force?: boolean; maxAgeMs?: number },
): Promise<T> {
  const force = options?.force ?? false;
  const maxAgeMs = options?.maxAgeMs ?? 0;

  if (!force) {
    const cached = readCache<T>(key);
    if (cached && isCacheFresh(cached, maxAgeMs)) {
      return Promise.resolve(cached.data);
    }
    const existing = inflight.get(key) as Promise<T> | undefined;
    if (existing) return existing;
  }

  const startEpoch = cacheEpoch;
  const promise = fetcher()
    .then((data) => {
      if (startEpoch === cacheEpoch) {
        writeCache(key, data);
      }
      return data;
    })
    .finally(() => {
      if (inflight.get(key) === promise) {
        inflight.delete(key);
      }
    });

  inflight.set(key, promise);
  return promise;
}
