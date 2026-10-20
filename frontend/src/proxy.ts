import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

/**
 * Next.js 16 proxy (the former `middleware.ts` convention).
 *
 * Authorization is NOT decided here. Clerk deprecated path matching via
 * `createRouteMatcher()` in favour of resource-based checks, so this file only
 * installs Clerk's request context (which `auth()` needs in Server Components)
 * and serves the `__clerk` handshake routes. Every protected server entrypoint
 * calls `requireSession()` from `@/lib/server-auth` itself.
 *
 * When Clerk is disabled (no publishable key), pass all requests through
 * untouched — local dev uses the backend X-Internal-Token and the app's own
 * `RequireAuth`/`api.ts` handle auth.
 */
const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const devModeEnabled = process.env.NODE_ENV !== "production";
const clockSkewInMs = Number(process.env.CLERK_CLOCK_SKEW_MS ?? "60000");

// Pass-through is strictly a dev-mode convenience.  In a production build the
// Clerk proxy always runs (even without a publishable key) so requests fail
// closed instead of silently trusting the client-side internal-token mode.
export default devModeEnabled && !clerkKey
  ? function proxy() {
      return NextResponse.next();
    }
  : clerkMiddleware({
      clockSkewInMs: Number.isFinite(clockSkewInMs) ? clockSkewInMs : 60_000,
    });

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
    "/__clerk/(.*)",
  ],
};
