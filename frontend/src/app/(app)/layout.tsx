import { AppShell } from "@/components/shell";
import { RequireAuth } from "@/components/require-auth";
import { requireSession } from "@/lib/server-auth";

// These are authenticated, per-user pages gated at request time.
// Force dynamic rendering so they are not statically prerendered at build
// (which crashes `useAuth` outside <ClerkProvider> during `next build`).
export const dynamic = "force-dynamic";

// eslint-disable-next-line @clerk/next/require-auth-protection -- Protected by requireSession(), the dev-mode-aware wrapper around auth.protect().
export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  // Resource-based check: redirects signed-out users to sign-in before any
  // child page renders. `RequireAuth` remains as the client-side loading gate.
  await requireSession();

  return (
    <AppShell>
      <RequireAuth>{children}</RequireAuth>
    </AppShell>
  );
}
