"use client";

import { useEffect, useState } from "react";
import { AuditLogsPanel } from "@/components/audit-logs";
import { ErrorBox, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

export default function ActivityPage() {
  usePageTitle("Activity");
  const [workspaceId, setWorkspaceId] = useState("");
  const [loading, setLoading] = useState(true);
  const [canView, setCanView] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadAccess() {
      try {
        const id = await ensureWorkspace();
        const me = await api.me();
        let allowed = me.is_internal;
        if (!allowed && me.id) {
          const members = await api.listMembers(id);
          const role = members.find((member) => member.user_id === me.id)?.role;
          allowed = role === "owner" || role === "admin";
        }
        if (!cancelled) {
          setWorkspaceId(id);
          setCanView(allowed);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not check workspace access.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadAccess();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader
        title="Workspace activity"
        description="Review administrative, authentication, and monitor events."
      />
      {error ? <ErrorBox message={error} /> : null}
      {loading ? <p className="text-sm text-[var(--ink-subtle)]">Checking workspace access…</p> : null}
      {!loading && !error && !canView ? (
        <p className="rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-1)] p-4 text-sm text-[var(--ink-muted)]">
          Workspace activity is available to admins and owners.
        </p>
      ) : null}
      {!loading && canView && workspaceId ? <AuditLogsPanel workspaceId={workspaceId} /> : null}
    </div>
  );
}
