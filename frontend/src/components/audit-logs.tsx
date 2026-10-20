"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, ErrorBox, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api";
import type { AuditLogRow } from "@/lib/types";

export function AuditLogsPanel({ workspaceId }: { workspaceId: string }) {
  const [logs, setLogs] = useState<AuditLogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setErr(null);
    try {
      const list = await api.listAuditLogs(workspaceId, { limit: 100 });
      setLogs(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <SectionTitle>Workspace audit logs</SectionTitle>
          <p className="text-xs text-[var(--ink-subtle)]">
            Immutable audit record of administrative, auth, and monitor events.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={loading}
          onClick={load}
        >
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </div>

      {err ? <ErrorBox message={err} /> : null}

      <Card className="space-y-3">
        {logs.length === 0 ? (
          <p className="rounded-[8px] border border-dashed border-[var(--hairline-strong)] px-3 py-6 text-center text-sm text-[var(--ink-subtle)]">
            {loading ? "Loading audit logs…" : "No audit entries recorded yet."}
          </p>
        ) : (
          <div className="divide-y divide-[var(--border)]">
            {logs.map((log) => (
              <div
                key={log.id}
                className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="info">{log.action}</Badge>
                    <span className="text-xs font-medium text-[var(--ink)]">
                      {log.resource_type}
                      {log.resource_id ? ` #${log.resource_id.slice(0, 8)}` : ""}
                    </span>
                    {log.actor_email ? (
                      <span className="text-xs text-[var(--ink-subtle)]">
                        by {log.actor_email}
                      </span>
                    ) : null}
                  </div>
                  {log.meta && Object.keys(log.meta).length > 0 ? (
                    <pre className="mt-1.5 max-w-full overflow-x-auto rounded-[6px] border border-[var(--hairline)] bg-[var(--surface-3)] p-2 font-mono text-xs text-[var(--ink)]">
                      {JSON.stringify(log.meta, null, 2)}
                    </pre>
                  ) : null}
                </div>
                <div className="text-right text-xs text-[var(--ink-subtle)]">
                  {new Date(log.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
