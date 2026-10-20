"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Input, Label, SectionTitle, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { InviteRow } from "@/lib/types";

const ROLES = ["member", "admin", "viewer", "owner"] as const;

export function TeamInvites({ workspaceId }: { workspaceId: string }) {
  const [invites, setInvites] = useState<InviteRow[]>([]);
  const [role, setRole] = useState<string>("member");
  const [maxUses, setMaxUses] = useState(5);
  const [expiresDays, setExpiresDays] = useState(7);
  const [creating, setCreating] = useState(false);
  const [generated, setGenerated] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!workspaceId) return;
    api
      .listInvites(workspaceId)
      .then(setInvites)
      .catch(() => setErr("Could not load invites."));
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    setCreating(true);
    setErr(null);
    setMsg(null);
    try {
      const r = await api.createInvite(workspaceId, {
        role,
        max_uses: maxUses,
        expires_days: expiresDays,
      });
      setGenerated(`${window.location.origin}${r.url}`);
      setMsg("Share the link below. The full token is shown only once.");
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to create invite");
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id: string) {
    try {
      await api.revokeInvite(workspaceId, id);
      setInvites((rows) => rows.filter((r) => r.id !== id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to revoke invite");
    }
  }

  function copy() {
    if (!generated) return;
    navigator.clipboard?.writeText(generated).then(
      () => setMsg("Copied to clipboard."),
      () => setMsg(generated),
    );
  }

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <SectionTitle>Team invite links</SectionTitle>
        <span className="text-xs text-[var(--ink-subtle)]">expiring · multi-use</span>
      </div>
      <p className="text-xs text-[var(--ink-subtle)]">
        Generate a link that lets teammates join this workspace. The token is hashed in our
        database and only shown once. Revoke anytime.
      </p>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <Label>Role</Label>
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label>Max uses</Label>
          <Input
            type="number"
            min={1}
            max={100}
            value={maxUses}
            onChange={(e) => setMaxUses(Number(e.target.value))}
            className="w-24"
          />
        </div>
        <div>
          <Label>Expires (days)</Label>
          <Input
            type="number"
            min={1}
            max={365}
            value={expiresDays}
            onChange={(e) => setExpiresDays(Number(e.target.value))}
            className="w-24"
          />
        </div>
        <Button type="button" variant="secondary" disabled={creating} onClick={create}>
          {creating ? "Generating…" : "Generate invite link"}
        </Button>
      </div>

      {generated ? (
        <div className="space-y-2 rounded-[8px] border border-[var(--primary)]/25 bg-[var(--surface-2)] p-3">
          <p className="break-all font-mono text-xs text-[var(--primary-hover)]">{generated}</p>
          <Button type="button" variant="ghost" size="sm" onClick={copy}>
            Copy link
          </Button>
        </div>
      ) : null}
      {msg ? <p className="text-sm text-[var(--semantic-success)]">{msg}</p> : null}
      {err ? <p className="text-sm text-[var(--danger)]">{err}</p> : null}

      <div className="space-y-2">
        {invites.length === 0 ? (
          <p className="rounded-[8px] border border-dashed border-[var(--hairline-strong)] px-3 py-5 text-center text-sm text-[var(--ink-subtle)]">
            No invite links yet.
          </p>
        ) : (
          invites.map((inv) => (
            <div
              key={inv.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-2)] px-3.5 py-2.5"
            >
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge tone="neutral">{inv.role}</Badge>
                <span className="text-[var(--ink-muted)]">
                  {inv.use_count}/{inv.max_uses} used
                </span>
                <span className="text-xs text-[var(--ink-subtle)] font-mono">{inv.token_prefix}…</span>
              </div>
              <Button type="button" variant="ghost" size="sm" onClick={() => revoke(inv.id)}>
                Revoke
              </Button>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
