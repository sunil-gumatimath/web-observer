/**
 * Lightweight workspace-scoped client cache with in-flight deduplication and
 * epoch + per-key ownership guards so switching tabs renders cached data
 * immediately while stale or invalidated requests can never overwrite newer state.
 */

export type CacheEntry<T> = {
  data: T;
  updatedAt: number;
};

type InflightEntry = {
  promise: Promise<unknown>;
  token: symbol;
};

const store = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, InflightEntry>();
const latestTokens = new Map<string, symbol>();
let cacheEpoch = 0;

function setStoreEntry<T>(key: string, data: T): CacheEntry<T> {
  const entry: CacheEntry<T> = { data, updatedAt: Date.now() };
  store.set(key, entry);
  return entry;
}

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

/** Write a value to the cache under the current epoch, superseding older fetches. */
export function writeCache<T>(key: string, data: T): CacheEntry<T> {
  latestTokens.set(key, Symbol("write"));
  inflight.delete(key);
  return setStoreEntry(key, data);
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
  latestTokens.clear();
}

/** Drop cached entries and invalidate matching in-flight requests by prefix. */
export function invalidateCachePrefix(prefix: string): void {
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) store.delete(key);
  }
  for (const key of inflight.keys()) {
    if (key.startsWith(prefix)) inflight.delete(key);
  }
  for (const key of latestTokens.keys()) {
    if (key.startsWith(prefix)) latestTokens.delete(key);
  }
}

/**
 * Fetch and cache a resource with in-flight request deduplication.
 *
 * - When `maxAgeMs > 0` and `force` is false, a fresh entry is returned
 *   without issuing a network request.
 * - Concurrent callers for the same `key` share one in-flight promise.
 * - If `clearQueryCache()`, `invalidateCachePrefix()`, or a newer forced
 *   request supersedes this call, its response is discarded instead of
 *   overwriting newer state.
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
    const existing = inflight.get(key);
    if (existing) return existing.promise as Promise<T>;
  }

  const startEpoch = cacheEpoch;
  const token = Symbol(key);
  latestTokens.set(key, token);

  const promise = fetcher()
    .then((data) => {
      if (startEpoch === cacheEpoch && latestTokens.get(key) === token) {
        setStoreEntry(key, data);
      }
      return data;
    })
    .finally(() => {
      if (inflight.get(key)?.token === token) {
        inflight.delete(key);
      }
    });

  inflight.set(key, { promise, token });
  return promise;
}
