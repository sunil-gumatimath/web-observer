/** Shared token getter so the API client can attach Clerk session tokens. */

type TokenGetter = () => Promise<string | null>;

let tokenGetter: TokenGetter | null = null;

/**
 * Current Clerk user id, used to key per-user caches (e.g. the resolved
 * workspace) so signing out or switching users can't leak the previous user's
 * data. `null` means signed out / unknown.
 */
let currentClerkUserId: string | null = null;

/** Clerk getToken() can hang if the Clerk network is slow — never wait forever. */
const TOKEN_TIMEOUT_MS = 5_000;

export function setAuthTokenGetter(getter: TokenGetter | null) {
  tokenGetter = getter;
}

/** Read the last-known Clerk user id (see `setClerkUserId`). */
export function getClerkUserId(): string | null {
  return currentClerkUserId;
}

/** Update the tracked Clerk user id. Pass `null` on sign-out. */
export function setClerkUserId(userId: string | null) {
  currentClerkUserId = userId;
}

function withTimeout<T>(promise: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise((resolve) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        resolve(fallback);
      }
    }, ms);
    promise
      .then((value) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve(value);
        }
      })
      .catch(() => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve(fallback);
        }
      });
  });
}

export async function getAuthToken(): Promise<string | null> {
  if (!tokenGetter) return null;
  try {
    return await withTimeout(tokenGetter(), TOKEN_TIMEOUT_MS, null);
  } catch {
    return null;
  }
}
