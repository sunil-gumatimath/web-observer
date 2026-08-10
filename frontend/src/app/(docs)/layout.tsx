import { AppShell } from "@/components/shell";

/**
 * Public docs layout: shows the app shell (theme toggle, nav, auth controls)
 * but skips RequireAuth so signed-out visitors can read the docs.
 */
export default function PublicDocsLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
