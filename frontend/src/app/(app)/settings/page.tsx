"use client";

import { useEffect, useState } from "react";
import { NotificationChannelsPanel } from "@/components/notification-channels";
import { TeamInvites } from "@/components/team-invites";
import { WorkspaceKeys } from "@/components/workspace-keys";
import { WorkspaceMembers } from "@/components/workspace-members";
import { AuditLogsPanel } from "@/components/audit-logs";
import { ConfirmButton } from "@/components/confirm-dialog";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  Input,
  Label,
  PageHeader,
  SectionTitle,
  Select,
  SuccessBox,
} from "@/components/ui";
import { api, type MeResponse } from "@/lib/api";
import type { ApiKeyRow, WebhookDelivery, WebhookOut } from "@/lib/types";
import { config } from "@/lib/config";
import { ensureWorkspace, getStoredWorkspaceId, setStoredWorkspaceId } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

export default function SettingsPage() {
  usePageTitle("Settings");

  const [workspaceId, setWorkspaceId] = useState("");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<string>("…");
  const [digestCadence, setDigestCadence] = useState("none");
  const [digestHour, setDigestHour] = useState(14);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [savingPrefs, setSavingPrefs] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => setApiStatus(`${h.status} v${h.version}`))
      .catch(() => setApiStatus("unreachable"));

    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));

    ensureWorkspace()
      .then(async (id) => {
        setWorkspaceId(id);
        try {
          const ws = await api.getWorkspace(id);
          setDigestCadence(ws.digest_cadence || "none");
          setDigestHour(ws.digest_hour_utc ?? 14);
          setAiEnabled(ws.ai_summaries_enabled !== false);
        } catch {
          /* ignore */
        }
      })
      .catch(() => {
        /* keep stored id */
      });
  }, []);

  async function seed() {
    setError(null);
    setMessage(null);
    try {
      const s = await api.seed();
      setStoredWorkspaceId(s.workspace_id);
      setWorkspaceId(s.workspace_id);
      setMessage(`Seeded workspace ${s.workspace_id} for ${s.email}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Seed failed");
    }
  }

  function saveWorkspace() {
    if (!workspaceId.trim()) return;
    setStoredWorkspaceId(workspaceId.trim());
    setMessage("Workspace ID saved in this browser.");
  }

  async function savePrefs() {
    if (!workspaceId) return;
    setSavingPrefs(true);
    setError(null);
    try {
      await api.updateWorkspace(workspaceId, {
        digest_cadence: digestCadence,
        digest_hour_utc: digestHour,
        ai_summaries_enabled: aiEnabled,
      });
      setMessage("Workspace preferences saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save preferences");
    } finally {
      setSavingPrefs(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Settings"
        description={
          config.clerkEnabled
            ? "Account, digests, AI summaries, and alert channels."
            : "Dev auth, digests, AI, and alert channels (email / Slack / Discord)."
        }
      />
      {error ? <ErrorBox message={error} /> : null}
      {message ? <SuccessBox message={message} /> : null}

      <div className="mb-6 space-y-6">
        <WorkspaceKeys workspaceId={workspaceId} />
        <TeamInvites workspaceId={workspaceId} />
      </div>

      <div className="grid max-w-2xl gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Card className="!p-4">
            <p className="section-label">API</p>
            <p className="mt-2 truncate text-sm font-medium text-slate-800 dark:text-slate-200">{config.apiBaseUrl}</p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
              Health:{" "}
              <span
                className={
                  apiStatus.startsWith("ok") || apiStatus.includes("ok")
                    ? "text-emerald-600 dark:text-emerald-400"
                    : apiStatus === "…"
                      ? "text-slate-500 dark:text-slate-500"
                      : "text-rose-600 dark:text-rose-400"
                }
              >
                {apiStatus}
              </span>
            </p>
          </Card>

          <Card className="!p-4">
            <p className="section-label">Auth mode</p>
            <p className="mt-2 text-sm font-medium text-slate-800 dark:text-slate-200">
              {config.clerkEnabled ? "Clerk (Bearer JWT)" : "Internal token (dev)"}
            </p>
            {me ? (
              <div className="mt-2 space-y-0.5 text-xs text-slate-600 dark:text-slate-400">
                <p>Email: {me.email ?? "—"}</p>
                <p>Internal: {me.is_internal ? "yes" : "no"}</p>
                <p className="truncate">
                  Workspaces: {me.workspaces.map((w) => w.name).join(", ") || "none"}
                </p>
              </div>
            ) : null}
          </Card>
        </div>

        <Card className="space-y-3">
          <div>
            <Label htmlFor="ws">Active workspace ID</Label>
            <Input
              id="ws"
              value={workspaceId}
              onChange={(e) => setWorkspaceId(e.target.value)}
              placeholder="UUID"
              className="font-mono text-xs"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={saveWorkspace}>
              Save workspace
            </Button>
            {!config.clerkEnabled ? (
              <Button type="button" variant="secondary" onClick={seed}>
                Seed dev workspace
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              onClick={async () => {
                try {
                  const id = await ensureWorkspace();
                  setWorkspaceId(id);
                  setMessage(`Using workspace ${id}`);
                  const m = await api.me();
                  setMe(m);
                } catch (e) {
                  setError(e instanceof Error ? e.message : "Failed");
                }
              }}
            >
              Ensure workspace
            </Button>
          </div>
        </Card>

        {workspaceId ? (
          <Card className="space-y-4">
            <p className="section-label">Preferences</p>
            <div>
              <Label htmlFor="digest">Email/Slack digest</Label>
              <Select
                id="digest"
                value={digestCadence}
                onChange={(e) => setDigestCadence(e.target.value)}
              >
                <option value="none">Off</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly (Mondays)</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="hour">Digest hour (UTC)</Label>
              <Input
                id="hour"
                type="number"
                min={0}
                max={23}
                value={digestHour}
                onChange={(e) => setDigestHour(Number(e.target.value))}
              />
            </div>
            <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--border)] bg-slate-50/60 px-3 py-2.5 text-sm text-slate-700 transition hover:border-slate-400 dark:bg-slate-950/40 dark:text-slate-300 dark:hover:border-white/10">
              <input
                type="checkbox"
                checked={aiEnabled}
                onChange={(e) => setAiEnabled(e.target.checked)}
                className="h-4 w-4 rounded border-slate-400 bg-white text-sky-500 focus:ring-sky-500/30 dark:border-slate-600 dark:bg-slate-900"
              />
              AI summaries & categories (optional LLM; heuristic if no key)
            </label>
            <Button type="button" disabled={savingPrefs} onClick={savePrefs}>
              {savingPrefs ? "Saving…" : "Save preferences"}
            </Button>
          </Card>
        ) : null}

        {workspaceId ? (
          <div>
            <SectionTitle>Alert channels</SectionTitle>
            <NotificationChannelsPanel workspaceId={workspaceId} />
          </div>
        ) : null}

        {workspaceId ? <WorkspaceMembers workspaceId={workspaceId} /> : null}

        {workspaceId ? <AuditLogsPanel workspaceId={workspaceId} /> : null}

        {workspaceId ? <EnterprisePanel workspaceId={workspaceId} /> : null}
      </div>
    </div>
  );
}

/** Optional tools for solo use — billing/plan upgrades are skipped. */
function EnterprisePanel({ workspaceId }: { workspaceId: string }) {
  const [apiKeyName, setApiKeyName] = useState("default");
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKeyRow[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);

  const [webhookSecret, setWebhookSecret] = useState<string | null>(null);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhooks, setWebhooks] = useState<WebhookOut[]>([]);
  const [webhooksLoading, setWebhooksLoading] = useState(false);

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [creatingKey, setCreatingKey] = useState(false);
  const [creatingWebhook, setCreatingWebhook] = useState(false);

  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [deliveriesLoading, setDeliveriesLoading] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  async function loadApiKeys() {
    setApiKeysLoading(true);
    try {
      const list = await api.listApiKeys(workspaceId);
      setApiKeys(list);
    } catch {
      /* non-fatal */
    } finally {
      setApiKeysLoading(false);
    }
  }

  async function deleteApiKey(keyId: string) {
    setErr(null);
    setMsg(null);
    try {
      await api.deleteApiKey(workspaceId, keyId);
      setApiKeys((prev) => prev.filter((k) => k.id !== keyId));
      setMsg("API key revoked.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to revoke API key");
    }
  }

  async function loadWebhooks() {
    setWebhooksLoading(true);
    try {
      const list = await api.listWebhooks(workspaceId);
      setWebhooks(list);
    } catch {
      /* non-fatal */
    } finally {
      setWebhooksLoading(false);
    }
  }

  async function deleteWebhook(endpointId: string) {
    setErr(null);
    setMsg(null);
    try {
      await api.deleteWebhook(workspaceId, endpointId);
      setWebhooks((prev) => prev.filter((w) => w.id !== endpointId));
      setMsg("Webhook deleted.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to delete webhook");
    }
  }

  async function loadDeliveries() {
    setDeliveriesLoading(true);
    try {
      const list = await api.listWebhookDeliveries(workspaceId, { limit: 50 });
      setDeliveries(list);
    } catch {
      /* non-fatal: keep any prior list */
    } finally {
      setDeliveriesLoading(false);
    }
  }

  useEffect(() => {
    if (workspaceId) {
      loadApiKeys();
      loadWebhooks();
      loadDeliveries();
    }
  }, [workspaceId]);

  async function retry(deliveryId: string) {
    setRetryingId(deliveryId);
    setErr(null);
    try {
      await api.retryWebhookDelivery(workspaceId, deliveryId);
      setMsg("Webhook delivery re-enqueued.");
      await loadDeliveries();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setRetryingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <SectionTitle>Optional: API keys & webhooks</SectionTitle>
      <p className="text-xs text-slate-500 dark:text-slate-500">
        API access tokens and outbound signed webhooks (HMAC-SHA256).
      </p>
      {err ? <ErrorBox message={err} /> : null}
      {msg ? <SuccessBox message={msg} /> : null}

      {/* API Keys Panel */}
      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <p className="section-label">API keys</p>
          <Button type="button" variant="secondary" size="sm" disabled={apiKeysLoading} onClick={loadApiKeys}>
            {apiKeysLoading ? "Loading…" : "Refresh"}
          </Button>
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <Label htmlFor="key-name">Key label</Label>
            <Input
              id="key-name"
              placeholder="e.g. CI/CD or CLI"
              value={apiKeyName}
              onChange={(e) => setApiKeyName(e.target.value)}
            />
          </div>
          <Button
            type="button"
            disabled={creatingKey || !apiKeyName.trim()}
            onClick={async () => {
              setErr(null);
              setCreatingKey(true);
              try {
                const r = await api.createApiKey(workspaceId, apiKeyName.trim());
                setApiKey(r.raw_key);
                setMsg("API key created — copy it now; it will not be shown again.");
                await loadApiKeys();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "API key failed");
              } finally {
                setCreatingKey(false);
              }
            }}
          >
            {creatingKey ? "Creating…" : "Create API key"}
          </Button>
        </div>

        {apiKey ? (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">
              Save your secret key now. It will never be shown again:
            </p>
            <p className="break-all rounded-lg border border-amber-500/30 bg-amber-500/15 p-3 font-mono text-xs text-amber-700 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
              {apiKey}
            </p>
          </div>
        ) : null}

        <div className="space-y-2">
          {apiKeys.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[var(--border-strong)] px-3 py-4 text-center text-xs text-slate-500 dark:text-slate-500">
              No API keys created yet.
            </p>
          ) : (
            apiKeys.map((k) => (
              <div
                key={k.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--border)] bg-slate-50/60 px-3 py-2.5 dark:bg-slate-950/40"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{k.name}</span>
                    <span className="font-mono text-xs text-slate-500">{k.key_prefix}…</span>
                  </div>
                  <p className="text-xs text-slate-400 dark:text-slate-500">
                    Created {new Date(k.created_at).toLocaleDateString()}
                    {k.last_used_at ? ` · Last used ${new Date(k.last_used_at).toLocaleDateString()}` : " · Never used"}
                  </p>
                </div>
                <ConfirmButton
                  variant="danger"
                  size="sm"
                  confirmLabel="Revoke"
                  title="Revoke API key?"
                  body={`Are you sure you want to revoke key "${k.name}"? Any clients using it will lose access.`}
                  onConfirm={() => deleteApiKey(k.id)}
                >
                  Revoke
                </ConfirmButton>
              </div>
            ))
          )}
        </div>
      </Card>

      {/* Webhooks Panel */}
      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <p className="section-label">Outbound Webhooks</p>
          <Button type="button" variant="secondary" size="sm" disabled={webhooksLoading} onClick={loadWebhooks}>
            {webhooksLoading ? "Loading…" : "Refresh"}
          </Button>
        </div>

        <div>
          <Label htmlFor="wh">Webhook URL (https)</Label>
          <div className="mt-1 flex gap-2">
            <Input
              id="wh"
              placeholder="https://example.com/webhooks/monitor-the-web"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
            />
            <Button
              type="button"
              disabled={creatingWebhook || !webhookUrl.trim()}
              onClick={async () => {
                setErr(null);
                setCreatingWebhook(true);
                try {
                  const r = await api.createWebhook(workspaceId, webhookUrl.trim());
                  setWebhookSecret(r.secret);
                  setMsg("Webhook created — store the signing secret securely.");
                  setWebhookUrl("");
                  await loadWebhooks();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "Webhook failed");
                } finally {
                  setCreatingWebhook(false);
                }
              }}
            >
              {creatingWebhook ? "Adding…" : "Add webhook"}
            </Button>
          </div>
        </div>

        {webhookSecret ? (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">
              Webhook signing secret (used for X-MTW-Signature HMAC):
            </p>
            <p className="break-all rounded-lg border border-amber-500/30 bg-amber-500/15 p-3 font-mono text-xs text-amber-700 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
              {webhookSecret}
            </p>
          </div>
        ) : null}

        <div className="space-y-2">
          {webhooks.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[var(--border-strong)] px-3 py-4 text-center text-xs text-slate-500 dark:text-slate-500">
              No webhooks registered yet.
            </p>
          ) : (
            webhooks.map((w) => (
              <div
                key={w.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--border)] bg-slate-50/60 px-3 py-2.5 dark:bg-slate-950/40"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Badge tone={w.enabled ? "success" : "neutral"}>{w.enabled ? "Active" : "Disabled"}</Badge>
                    <span className="truncate font-mono text-xs text-slate-900 dark:text-slate-100">{w.url}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
                    Added {new Date(w.created_at).toLocaleDateString()}
                  </p>
                </div>
                <ConfirmButton
                  variant="danger"
                  size="sm"
                  confirmLabel="Delete"
                  title="Delete webhook?"
                  body="Are you sure you want to delete this webhook endpoint?"
                  onConfirm={() => deleteWebhook(w.id)}
                >
                  Delete
                </ConfirmButton>
              </div>
            ))
          )}
        </div>
      </Card>

      {/* Webhook Deliveries Log */}
      <Card className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="section-label">Webhook deliveries</p>
          <Button type="button" variant="secondary" size="sm" disabled={deliveriesLoading} onClick={loadDeliveries}>
            {deliveriesLoading ? "Loading…" : "Refresh"}
          </Button>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-500">
          Outbound change webhooks and their delivery status. Retry re-sends a failed or stuck delivery.
        </p>
        <div className="space-y-2">
          {deliveries.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[var(--border-strong)] px-3 py-6 text-center text-sm text-slate-500 dark:text-slate-500">
              No deliveries yet. Click Refresh after change events fire.
            </p>
          ) : (
            deliveries.map((d) => (
              <div
                key={d.id}
                className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-[var(--border)] bg-slate-50/60 px-3.5 py-3 dark:bg-slate-950/40"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={d.status === "sent" ? "success" : d.status === "failed" ? "danger" : "warn"}>
                      {d.status}
                    </Badge>
                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{d.event_type}</span>
                  </div>
                  <p className="mt-1 truncate font-mono text-xs text-slate-500 dark:text-slate-500">{d.id}</p>
                  {d.last_error ? (
                    <p className="mt-1 line-clamp-2 text-xs text-rose-600 dark:text-rose-400">{d.last_error}</p>
                  ) : null}
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
                    attempts: {d.attempts}
                    {d.response_code != null ? ` · HTTP ${d.response_code}` : ""} ·{" "}
                    {new Date(d.created_at).toLocaleString()}
                  </p>
                </div>
                {d.status !== "sent" ? (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={retryingId === d.id}
                    onClick={() => retry(d.id)}
                  >
                    {retryingId === d.id ? "Retrying…" : "Retry"}
                  </Button>
                ) : null}
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
