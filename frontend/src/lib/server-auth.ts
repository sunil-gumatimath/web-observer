import { auth } from "@clerk/nextjs/server";
import { config } from "@/lib/config";

/**
 * Server-side session gate for authenticated routes.
 *
 * Clerk deprecated route-matching in `proxy.ts` (`createRouteMatcher`) in favour
 * of resource-based checks: each server entrypoint that serves protected content
 * calls `auth.protect()` itself. This helper wraps that call with one
 * project-specific condition — the internal-token dev mode, where Clerk is not
 * configured and pages authenticate against the backend instead.
 *
 * In a production build `config.useClerkAuth` is always true, so this fails
 * closed even when the publishable key is missing.
 *
 * ESLint's `@clerk/next/require-auth-protection` rule cannot see through this
 * wrapper, so call sites carry a disable comment with this reason.
 */
export async function requireSession(): Promise<void> {
  if (!config.useClerkAuth) return;
  await auth.protect();
}
