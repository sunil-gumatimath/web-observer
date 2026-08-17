import { AppShell } from "@/components/shell";

// AppShell calls Clerk's useAuth(); force dynamic so this route is not
// statically prerendered at build (which crashes useAuth outside
// <ClerkProvider> during `next build`).
export const dynamic = "force-dynamic";

/**
 * Public docs layout: shows the app shell (theme toggle, nav, auth controls)
 * but skips RequireAuth so signed-out visitors can read the docs.
 */
export default function PublicDocsLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
