import { AppShell } from "@/components/shell";
import { RequireAuth } from "@/components/require-auth";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <RequireAuth>{children}</RequireAuth>
    </AppShell>
  );
}
