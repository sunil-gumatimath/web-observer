export const config = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8002",
  internalToken: process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN ?? "dev-internal-token",
  devWorkspaceId: process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID ?? "",
  clerkPublishableKey: process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "",
  /**
   * Internal-token (no-Clerk) auth is a development convenience.  It must
   * NEVER be reachable in a production build — otherwise a misconfigured prod
   * (missing publishable key) silently falls back to the shared internal token
   * and exposes every workspace.  Gating on NODE_ENV makes the app fail closed:
   * in production the Clerk path is used unconditionally and a missing key just
   * means "not signed in".
   */
  devModeEnabled: process.env.NODE_ENV !== "production",
  get clerkEnabled() {
    return Boolean(this.clerkPublishableKey);
  },
  /** Clerk auth (JWT) is used whenever Clerk is configured OR in production. */
  get useClerkAuth() {
    return Boolean(this.clerkPublishableKey) || !this.devModeEnabled;
  },
};
