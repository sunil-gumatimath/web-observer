"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, ErrorBox, Label, SectionTitle, Select, SuccessBox } from "@/components/ui";
import { ConfirmButton } from "@/components/confirm-dialog";
import { api } from "@/lib/api";
import type { WorkspaceMemberRow } from "@/lib/types";

const ROLES = ["owner", "admin", "member", "viewer"] as const;

export function WorkspaceMembers({ workspaceId }: { workspaceId: string }) {
  const [members, setMembers] = useState<WorkspaceMemberRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      const list = await api.listMembers(workspaceId);
      setMembers(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load members");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRoleChange(userId: string, newRole: string) {
    setUpdatingId(userId);
    setErr(null);
    setMsg(null);
    try {
      const updated = await api.updateMemberRole(workspaceId, userId, newRole);
      setMembers((prev) =>
        prev.map((m) => (m.user_id === userId ? { ...m, role: updated.role } : m))
      );
      setMsg(`Role updated to ${newRole}.`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to update role");
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleRemove(userId: string) {
    setErr(null);
    setMsg(null);
    try {
      await api.removeMember(workspaceId, userId);
      setMembers((prev) => prev.filter((m) => m.user_id !== userId));
      setMsg("Member removed from workspace.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to remove member");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <SectionTitle>Team members & roles</SectionTitle>
          <p className="text-xs text-slate-500 dark:text-slate-500">
            Manage existing workspace members and adjust their permission levels.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={loading}
          onClick={load}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {err ? <ErrorBox message={err} /> : null}
      {msg ? <SuccessBox message={msg} /> : null}

      <Card className="space-y-3">
        {members.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[var(--border-strong)] px-3 py-6 text-center text-sm text-slate-500 dark:text-slate-500">
            {loading ? "Loading members…" : "No members found."}
          </p>
        ) : (
          <div className="divide-y divide-[var(--border)]">
            {members.map((m) => (
              <div
                key={m.user_id}
                className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-[var(--fg)]">
                      {m.email || "User"}
                    </span>
                    <Badge tone={m.role === "owner" ? "warn" : m.role === "admin" ? "info" : "neutral"}>
                      {m.role}
                    </Badge>
                  </div>
                  <p className="mt-0.5 truncate font-mono text-xs text-slate-400 dark:text-slate-500">
                    ID: {m.user_id}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <div className="w-28">
                    <Select
                      value={m.role}
                      disabled={updatingId === m.user_id}
                      onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </Select>
                  </div>

                  <ConfirmButton
                    variant="danger"
                    size="sm"
                    confirmLabel="Remove"
                    title="Remove member?"
                    body={`Are you sure you want to remove ${m.email || "this member"} from the workspace?`}
                    onConfirm={() => handleRemove(m.user_id)}
                  >
                    Remove
                  </ConfirmButton>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
