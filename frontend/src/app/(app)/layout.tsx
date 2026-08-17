import { AppShell } from "@/components/shell";
import { RequireAuth } from "@/components/require-auth";

// These are authenticated, per-user pages gated by Clerk at request time.
// Force dynamic rendering so they are not statically prerendered at build
// (which crashes `useAuth` outside <ClerkProvider> during `next build`).
export const dynamic = "force-dynamic";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <RequireAuth>{children}</RequireAuth>
    </AppShell>
  );
}
