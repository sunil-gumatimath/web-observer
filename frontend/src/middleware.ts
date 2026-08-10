import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

/**
 * Server-side route protection via Clerk.
 * When Clerk is disabled (no publishable key), pass all requests through
 * untouched — local dev uses the backend X-Internal-Token and the app's own
 * `RequireAuth`/`api.ts` handle auth, so no server redirect is needed.
 */
const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/docs(.*)",
  "/api/health(.*)",
]);

const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export default clerkKey
  ? clerkMiddleware(async (auth, req: NextRequest) => {
      if (!isPublicRoute(req)) {
        await auth.protect();
      }
    })
  : function middleware() {
      return NextResponse.next();
    };

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
