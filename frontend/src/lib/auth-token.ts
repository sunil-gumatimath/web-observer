/** Shared token getter so the API client can attach Clerk session tokens. */

type TokenGetter = () => Promise<string | null>;

let tokenGetter: TokenGetter | null = null;

/** Clerk getToken() can hang if the Clerk network is slow — never wait forever. */
const TOKEN_TIMEOUT_MS = 5_000;

export function setAuthTokenGetter(getter: TokenGetter | null) {
  tokenGetter = getter;
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
