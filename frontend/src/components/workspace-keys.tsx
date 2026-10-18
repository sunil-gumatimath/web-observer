"use client";

import { useEffect, useState } from "react";
import { Button, Card, Input, Label, SectionTitle, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { WorkspaceSettings } from "@/lib/types";

// Live Kilo Gateway catalog filtered to $0 input/output models
// (`isFree: true` at https://api.kilo.ai/api/gateway/models, checked 2026-10-19).
//
// Order is a Jev (jev-1.13.0) ranking pass over the free set for this app's job
// (short factual diff summaries within ~200-300 output tokens), best first.
// Trailing numbers are Jev's 0-4 fitness score; the top band is solid, the
// middle band is low-confidence and shifted on a second pass, so don't read
// close gaps in it as meaningful. This ordering is presentational only — the
// server default (llm_model) is unchanged.
const FREE_MODELS: Array<{ value: string; label: string }> = [
  // Best fits — Jev 2.7-3.0, each returned a correct sentence in a live probe.
  { value: "reflection/beam-free", label: "Beam 1.0 (free) — Reflection · 1M ctx" }, // 2.95
  { value: "poolside/laguna-s-2.1:free", label: "Laguna S 2.1 (free) — Poolside · Coding · 262K ctx" }, // 2.90
  { value: "nvidia/nemotron-3-ultra-550b-a55b:free", label: "Nemotron 3 Ultra (free) — NVIDIA · 550B · 1M ctx" }, // 2.82
  { value: "stealth/glyph-cluster", label: "Glyph Cluster (free) — Stealth · 256K ctx" }, // 2.72
  // Workable — Jev 2.2-2.5; several of these scored lower on a second pass.
  { value: "cohere/north-mini-code:free", label: "North Mini Code (free) — Cohere · Coding · 256K ctx" }, // 2.54
  { value: "kilo-auto/free", label: "Auto Free — Kilo · Server default router · 256K ctx" }, // 2.47
  { value: "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", label: "Nemotron 3 Nano Omni (free) — NVIDIA · Multimodal · 256K ctx" }, // 2.45
  { value: "nvidia/nemotron-3.5-super-vl:free", label: "Nemotron 3.5 Super VL (free) — NVIDIA · Vision · Video · 1M ctx" }, // 2.38
  { value: "dots-studio/dots-3-note-preview:free", label: "Dots3-Note Preview (free) — Dots Studio · Vision · 512K ctx" }, // 2.20
  // Poor or failing — Jev 0.0-1.0; kept selectable, but prefer options above.
  { value: "poolside/laguna-xs-2.1:free", label: "Laguna XS 2.1 (free) — Poolside · Coding · 262K ctx" }, // 0.96
  { value: "nvidia/nemotron-3-super-120b-a12b:free", label: "Nemotron 3 Super (free) — NVIDIA · 120B · 262K ctx" }, // 0.94
  { value: "thinkingmachines/inkling-small:free", label: "Inkling Small (free) — Thinking Machines · Multimodal · 1M ctx" }, // 0.94
  { value: "openrouter/free", label: "Free Models Router — OpenRouter · Vision · 200K ctx" }, // 0.74
  { value: "xingchen-agi/xing4.0-29b-a4b:free", label: "Xing4.0 29B A4B (free) — XingChen · Reasoning · 262K ctx" }, // 0.41
  { value: "nvidia/nemotron-3.5-lightning:free", label: "Nemotron 3.5 Lightning (free) — NVIDIA · Reasoning · 1M ctx" }, // 0.00 — empty output at app token cap
  { value: "liquid/lfm-2.5-2.6b:free", label: "LFM2.5-2.6B (free) — Liquid AI · Lightweight · 65K ctx" }, // 0.00 — empty output at app token cap
  { value: "nvidia/nemotron-3.5-content-safety:free", label: "Nemotron 3.5 Content Safety (free) — NVIDIA · Moderation · 128K ctx" }, // 0.00 — moderation model, not a summariser
];

const LLM_BASE_PRESETS = ["https://api.kilo.ai/api/gateway", "https://api.openai.com/v1"] as const;

export function WorkspaceKeys({ workspaceId }: { workspaceId: string }) {
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
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

  const isCustomModel = Boolean(forceCustom || (llmModel && !FREE_MODELS.some((m) => m.value === llmModel)));
  const modelSelectValue = isCustomModel ? "__custom__" : llmModel;

  const isCustomBase = Boolean(forceCustomBase || (llmBase && !LLM_BASE_PRESETS.includes(llmBase as (typeof LLM_BASE_PRESETS)[number])));
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

  // keep forceCustom in sync when model/base is typed to a custom value
  useEffect(() => {
    if (llmModel && !FREE_MODELS.some((m) => m.value === llmModel)) {
      setForceCustom(true);
    }
  }, [llmModel]);

  useEffect(() => {
    if (llmBase && !LLM_BASE_PRESETS.includes(llmBase as (typeof LLM_BASE_PRESETS)[number])) {
      setForceCustomBase(true);
    }
  }, [llmBase]);

  if (!settings) {
    return (
      <Card>
        <SectionTitle>Bring-your-own keys</SectionTitle>
        <p className="text-sm text-slate-500">Loading…</p>
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
        <span className="text-xs text-slate-500">per workspace</span>
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-500">
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
              }
            }}
          >
            <option value="">-- Use server default (https://api.kilo.ai/api/gateway) --</option>
            <option value="https://api.kilo.ai/api/gateway">Kilo Gateway — https://api.kilo.ai/api/gateway (for :free models)</option>
            <option value="https://api.openai.com/v1">OpenAI — https://api.openai.com/v1</option>
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
          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
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
            {FREE_MODELS.map((m) => (
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
          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
            Free Kilo Gateway models ($0 input/output).{" "}
            <a
              href="https://kilo.ai/landing/free-models"
              target="_blank"
              rel="noreferrer"
              className="underline hover:text-[var(--accent)]"
            >
              View live catalog
            </a>
            {settings.llm_model ? ` · current: ${settings.llm_model}` : ""}
          </p>
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

      {err ? <p className="text-sm text-rose-600 dark:text-rose-400">{err}</p> : null}
      {msg ? <p className="text-sm text-emerald-700 dark:text-emerald-300">{msg}</p> : null}

      <div className="flex items-center gap-3">
        <Button type="button" variant="secondary" disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save keys"}
        </Button>
        <span className="text-xs text-slate-500">
          AI summaries/triage and email alerts use these when set.
        </span>
      </div>
    </Card>
  );
}