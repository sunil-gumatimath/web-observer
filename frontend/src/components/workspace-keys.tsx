"use client";

import { useEffect, useState } from "react";
import { Button, Card, Input, Label, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api";
import type { WorkspaceSettings } from "@/lib/types";

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
      if (llmBase.trim() !== settings.llm_api_base) body.llm_api_base = llmBase.trim();
      if (llmModel.trim()) body.llm_model = llmModel.trim();
      if (resendKey.trim()) body.resend_api_key = resendKey.trim();
      if (typeof resendKey === "string" && resendKey.trim() === "" && settings.as_resend_api_key) {
        body.resend_api_key = "";
      }
      if (emailFrom.trim() !== settings.email_from) body.email_from = emailFrom.trim();
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
          <Input
            placeholder="https://api.openai.com/v1"
            value={llmBase}
            onChange={(e) => setLlmBase(e.target.value)}
          />
        </div>
        <div>
          <Label>LLM model</Label>
          <Input
            placeholder="gpt-4o-mini"
            value={llmModel}
            onChange={(e) => setLlmModel(e.target.value)}
          />
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