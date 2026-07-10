"use client";

import { useEffect, useState } from "react";
import { NotificationChannelsPanel } from "@/components/notification-channels";
import {
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
import { config } from "@/lib/config";
import { ensureWorkspace, getStoredWorkspaceId, setStoredWorkspaceId } from "@/lib/workspace";

export default function SettingsPage() {
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
    setWorkspaceId(getStoredWorkspaceId() ?? "");
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

      <div className="grid max-w-2xl gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Card className="!p-4">
            <p className="section-label">API</p>
            <p className="mt-2 truncate text-sm font-medium text-slate-200">{config.apiBaseUrl}</p>
            <p className="mt-1 text-xs text-slate-500">
              Health:{" "}
              <span
                className={
                  apiStatus.startsWith("ok") || apiStatus.includes("ok")
                    ? "text-emerald-400"
                    : apiStatus === "…"
                      ? "text-slate-500"
                      : "text-rose-400"
                }
              >
                {apiStatus}
              </span>
            </p>
          </Card>

          <Card className="!p-4">
            <p className="section-label">Auth mode</p>
            <p className="mt-2 text-sm font-medium text-slate-200">
              {config.clerkEnabled ? "Clerk (Bearer JWT)" : "Internal token (dev)"}
            </p>
            {me ? (
              <div className="mt-2 space-y-0.5 text-xs text-slate-400">
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
            <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-white/5 bg-slate-950/40 px-3 py-2.5 text-sm text-slate-300 transition hover:border-white/10">
              <input
                type="checkbox"
                checked={aiEnabled}
                onChange={(e) => setAiEnabled(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-sky-500 focus:ring-sky-500/30"
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

        {workspaceId ? <EnterprisePanel workspaceId={workspaceId} /> : null}
      </div>
    </div>
  );
}

/** Optional tools for solo use — billing/plan upgrades are skipped. */
function EnterprisePanel({ workspaceId }: { workspaceId: string }) {
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [webhookSecret, setWebhookSecret] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [webhookUrl, setWebhookUrl] = useState("https://example.com/hooks/mtw");

  async function authed(path: string, init?: RequestInit) {
    const res = await fetch(`${config.apiBaseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Token": config.internalToken,
        ...(init?.headers || {}),
      },
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(JSON.stringify(body.detail ?? body));
    return body;
  }

  return (
    <div className="space-y-4">
      <SectionTitle>Optional: API keys & webhooks</SectionTitle>
      <p className="text-xs text-slate-500">
        Billing is disabled for solo use. Free plan already includes full personal limits.
      </p>
      {err ? <ErrorBox message={err} /> : null}
      {msg ? <SuccessBox message={msg} /> : null}
      <Card className="space-y-3">
        <Button
          type="button"
          onClick={async () => {
            setErr(null);
            try {
              const r = await authed(`/api/v1/workspaces/${workspaceId}/api-keys`, {
                method: "POST",
                body: JSON.stringify({ name: "default" }),
              });
              setApiKey(r.raw_key);
              setMsg("API key created — copy it now; it will not be shown again.");
            } catch (e) {
              setErr(e instanceof Error ? e.message : "API key failed");
            }
          }}
        >
          Create API key
        </Button>
        {apiKey ? (
          <p className="break-all rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 font-mono text-xs text-amber-200">
            {apiKey}
          </p>
        ) : null}
      </Card>
      <Card className="space-y-3">
        <Label htmlFor="wh">Webhook URL (https) — optional</Label>
        <Input id="wh" value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} />
        <Button
          type="button"
          onClick={async () => {
            setErr(null);
            try {
              const r = await authed(`/api/v1/workspaces/${workspaceId}/webhooks`, {
                method: "POST",
                body: JSON.stringify({ url: webhookUrl }),
              });
              setWebhookSecret(r.secret);
              setMsg("Webhook created — store the signing secret securely.");
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Webhook failed");
            }
          }}
        >
          Add webhook
        </Button>
        {webhookSecret ? (
          <p className="break-all rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 font-mono text-xs text-amber-200">
            secret: {webhookSecret}
          </p>
        ) : null}
      </Card>
    </div>
  );
}
