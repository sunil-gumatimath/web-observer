"use client";

import { useEffect, useState } from "react";
import { AuditLogsPanel } from "@/components/audit-logs";
import { ErrorBox, PageHeader } from "@/components/ui";
import { api, type MeResponse } from "@/lib/api";
import { ensureWorkspace, getCachedMe } from "@/lib/workspace";
import { fetchCached, readCache } from "@/lib/query-cache";
import { cacheKeys } from "@/lib/route-prefetch";
import { usePageTitle } from "@/lib/use-page-title";
import type { WorkspaceMemberRow } from "@/lib/types";

export default function ActivityPage() {
  usePageTitle("Activity");
  const initialWs = readCache<string>("activeWorkspaceId")?.data ?? "";
  const initialMe = readCache<MeResponse>(cacheKeys.me())?.data;
  const initialMembers = initialWs
    ? readCache<WorkspaceMemberRow[]>(cacheKeys.members(initialWs))?.data
    : undefined;
  const initialCanView = (() => {
    if (!initialMe) return null;
    if (initialMe.is_internal) return true;
    if (!initialMe.id || !initialMembers) return null;
    const role = initialMembers.find((m) => m.user_id === initialMe.id)?.role;
    return role === "owner" || role === "admin";
  })();

  const [workspaceId, setWorkspaceId] = useState(initialWs);
  const [loading, setLoading] = useState(initialCanView === null);
  const [canView, setCanView] = useState(initialCanView ?? false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadAccess() {
      try {
        const id = await ensureWorkspace();
        const me = await getCachedMe({ maxAgeMs: 30_000 });
        let allowed = me.is_internal;
        if (!allowed && me.id) {
          const members = await fetchCached(
            cacheKeys.members(id),
            () => api.listMembers(id),
            { maxAgeMs: 30_000 },
          );
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
