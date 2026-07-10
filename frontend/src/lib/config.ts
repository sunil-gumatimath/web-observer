export const config = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  internalToken: process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN ?? "dev-internal-token",
  devWorkspaceId: process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID ?? "",
  clerkPublishableKey: process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "",
  get clerkEnabled() {
    return Boolean(this.clerkPublishableKey);
  },
};
