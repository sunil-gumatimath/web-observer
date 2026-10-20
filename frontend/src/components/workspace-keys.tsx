"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, Card, Input, Label, SectionTitle, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { CatalogProvider, ModelCatalog, WorkspaceSettings } from "@/lib/types";

// The selectable models come from the server catalog
// (GET /api/v1/model-catalog), which is the single source of truth shared with
// the backend's failover logic. Nothing about the provider list is hard-coded
// here, so the picker cannot drift from what the backend will actually try.
const OPENAI_BASE = "https://api.openai.com/v1";

function normalizeBase(base: string | null | undefined): string {
  return (base || "").trim().replace(/\/+$/, "");
}

export function WorkspaceKeys({ workspaceId }: { workspaceId: string }) {
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [llmKey, setLlmKey] = useState("");
  const [llmBase, setLlmBase] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [resendKey, setResendKey] = useState("");
  const [emailFrom, setEmailFrom] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [forceCustom, setForceCustom] = useState(false);
  const [forceCustomBase, setForceCustomBase] = useState(false);

  // The provider whose base URL matches the current selection. Models are
  // filtered to that provider so a model id is never paired with a base that
  // does not serve it.
  const provider = useMemo<CatalogProvider | null>(() => {
    if (!catalog) return null;
    const base = normalizeBase(llmBase);
    if (!base) return catalog.providers[0] ?? null;
    return (
      catalog.providers.find((p) => normalizeBase(p.base) === base) ??
      catalog.providers.find((p) => normalizeBase(p.base).includes("kilo.ai")) ??
      null
    );
  }, [catalog, llmBase]);

  const models = useMemo(() => provider?.models ?? [], [provider]);

  // Bases offered in the picker: every catalog provider plus first-party
  // OpenAI (which has no catalog entry because the app ships no OpenAI models).
  const basePresets = useMemo(
    () => [...(catalog?.providers ?? []).map((p) => p.base), OPENAI_BASE],
    [catalog],
  );

  const isCustomModel = Boolean(forceCustom || (llmModel && !models.some((m) => m.value === llmModel)));
  const modelSelectValue = isCustomModel ? "__custom__" : llmModel;

  const isCustomBase = Boolean(
    forceCustomBase || (llmBase && !basePresets.includes(llmBase)),
  );
  const baseSelectValue = isCustomBase ? "__custom__" : llmBase;

  useEffect(() => {
    if (!workspaceId) return;
    api
      .getWorkspaceSettings(workspaceId)
      .then((s) => {
        setSettings(s);
        setLlmBase(s.llm_api_base ?? "");
        setLlmModel(s.llm_model ?? "");
        setEmailFrom(s.email_from ?? "");
      })
      .catch(() => setErr("Could not load workspace settings."));
  }, [workspaceId]);

  useEffect(() => {
    api
      .getModelCatalog()
      .then(setCatalog)
      .catch(() => setErr("Could not load the model catalog."));
  }, []);

  // keep forceCustom in sync when model/base is typed to a custom value
  useEffect(() => {
    if (llmModel && models.length > 0 && !models.some((m) => m.value === llmModel)) {
      setForceCustom(true);
    }
  }, [llmModel, models]);

  useEffect(() => {
    if (llmBase && basePresets.length > 0 && !basePresets.includes(llmBase)) {
      setForceCustomBase(true);
    }
  }, [llmBase, basePresets]);

  if (!settings) {
    return (
      <Card>
        <SectionTitle>Bring-your-own keys</SectionTitle>
        <p className="text-sm text-[var(--ink-subtle)]">Loading…</p>
      </Card>
    );
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    setErr(null);
    setMsg(null);
    try {
      const body: Record<string, string | undefined> = {};
      if (llmKey.trim()) body.llm_api_key = llmKey.trim();
      if (typeof llmKey === "string" && llmKey.trim() === "" && settings.as_llm_api_key) {
        body.llm_api_key = "";
      }
      if ((llmBase.trim() || "") !== (settings.llm_api_base || "")) body.llm_api_base = llmBase.trim();
      if ((llmModel.trim() || "") !== (settings.llm_model || "")) body.llm_model = llmModel.trim();
      if (resendKey.trim()) body.resend_api_key = resendKey.trim();
      if (typeof resendKey === "string" && resendKey.trim() === "" && settings.as_resend_api_key) {
        body.resend_api_key = "";
      }
      if ((emailFrom.trim() || "") !== (settings.email_from || "")) body.email_from = emailFrom.trim();
      await api.updateWorkspaceKeys(workspaceId, body);
      setMsg("Keys saved. Note: API keys are never returned by the server.");
      setLlmKey("");
      setResendKey("");
      const fresh = await api.getWorkspaceSettings(workspaceId);
      setSettings(fresh);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save keys");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <SectionTitle>Bring-your-own keys</SectionTitle>
        <span className="text-xs text-[var(--ink-subtle)]">per workspace</span>
      </div>
      <p className="text-xs text-[var(--ink-subtle)]">
        Set your own LLM and Resend keys in Settings that override the server defaults
        (webdog.ai-style managed-or-self-serve). Stored keys are only ever returned as a
        “is set” flag, never revealed.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label>LLM API key</Label>
          <Input
            type="password"
            placeholder={settings.as_llm_api_key ? "•••••••• (set - type to replace)" : "sk-…"}
            value={llmKey}
            onChange={(e) => setLlmKey(e.target.value)}
            autoComplete="off"
          />
        </div>
        <div>
          <Label>Resend API key (email)</Label>
          <Input
            type="password"
            placeholder={settings.as_resend_api_key ? "•••••••• (set - type to replace)" : "re_…"}
            value={resendKey}
            onChange={(e) => setResendKey(e.target.value)}
            autoComplete="off"
          />
        </div>
        <div>
          <Label>LLM base URL</Label>
          <Select
            value={baseSelectValue}
            onChange={(e) => {
              const v = e.target.value;
              if (v === "__custom__") {
                setForceCustomBase(true);
                if (!isCustomBase) setLlmBase("");
              } else {
                setForceCustomBase(false);
                setLlmBase(v);
                // A model id belongs to one provider. Drop a model that the
                // newly selected base cannot serve, so the picker never offers
                // a mismatched pair.
                const nextProvider = catalog?.providers.find(
                  (p) => normalizeBase(p.base) === normalizeBase(v),
                );
                if (
                  nextProvider &&
                  llmModel &&
                  !nextProvider.models.some((m) => m.value === llmModel)
                ) {
                  setLlmModel("");
                  setForceCustom(false);
                }
              }
            }}
          >
            <option value="">-- Use server default (https://api.kilo.ai/api/gateway) --</option>
            {(catalog?.providers ?? []).map((p) => (
              <option key={p.id} value={p.base}>
                {p.label} — {p.base}
              </option>
            ))}
            <option value={OPENAI_BASE}>OpenAI — {OPENAI_BASE}</option>
            <option value="__custom__">Custom…</option>
          </Select>
          {isCustomBase ? (
            <Input
              className="mt-2"
              placeholder="https://your-gateway.example.com/v1"
              value={llmBase}
              onChange={(e) => setLlmBase(e.target.value)}
            />
          ) : null}
          <p className="mt-1 text-[11px] text-[var(--ink-subtle)]">
            Must match provider. <code>:free</code> models require Kilo Gateway. Current: {settings.llm_api_base || "—"}
          </p>
        </div>
        <div>
          <Label>LLM model</Label>
          <Select
            value={modelSelectValue}
            onChange={(e) => {
              const v = e.target.value;
              if (v === "__custom__") {
                setForceCustom(true);
                if (!isCustomModel) setLlmModel("");
              } else {
                setForceCustom(false);
                setLlmModel(v);
              }
            }}
          >
            <option value="">-- Use server default --</option>
            {models.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
            <option value="__custom__">Custom…</option>
          </Select>
          {isCustomModel ? (
            <Input
              className="mt-2"
              placeholder="custom/model-name  e.g. openai/gpt-4o-mini"
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
            />
          ) : null}
          <p className="mt-1 text-[11px] text-[var(--ink-subtle)]">
            {provider
              ? provider.free
                ? "Free models ($0 input/output). "
                : "Your own API key — usage is billed to you. "
              : "Loading models… "}
            {provider?.id === "kilo" ? (
              <a
                href="https://kilo.ai/landing/free-models"
                target="_blank"
                rel="noreferrer"
                className="underline hover:text-[var(--primary)]"
              >
                View live catalog
              </a>
            ) : null}
            {settings.llm_model ? ` · current: ${settings.llm_model}` : ""}
          </p>
          {provider?.models.some((m) => m.verified_at === null) ? (
            <p className="mt-1 text-[11px] text-[var(--ink-subtle)]">
              Models marked “needs a larger output cap” never returned a complete
              summary at any tested budget and can come back empty. Models with a
              higher cap are handled automatically.
            </p>
          ) : null}
        </div>
        <div className="sm:col-span-2">
          <Label>Email from (sender)</Label>
          <Input
            placeholder="alerts@yourdomain.com"
            value={emailFrom}
            onChange={(e) => setEmailFrom(e.target.value)}
          />
        </div>
      </div>

      {err ? <p className="text-sm text-[var(--danger)]">{err}</p> : null}
      {msg ? <p className="text-sm text-[var(--semantic-success)]">{msg}</p> : null}

      <div className="flex items-center gap-3">
        <Button type="button" variant="secondary" disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save keys"}
        </Button>
        <span className="text-xs text-[var(--ink-subtle)]">
          AI summaries/triage and email alerts use these when set.
        </span>
      </div>
    </Card>
  );
}