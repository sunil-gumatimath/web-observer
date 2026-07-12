"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  PageHeader,
  SectionTitle,
  Spinner,
} from "@/components/ui";
import { ReadableContent } from "@/components/readable-content";
import { api } from "@/lib/api";
import type { ChangeEventDetail } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

export default function ChangeDetailPage() {
  usePageTitle("Change detail");

  const params = useParams<{ id: string }>();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [change, setChange] = useState<ChangeEventDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ws = await ensureWorkspace();
        const c = await api.getChange(ws, params.id);
        if (!cancelled) {
          setWorkspaceId(ws);
          setChange(c);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load change");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  async function toggleNoise() {
    if (!workspaceId || !change) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.markChangeNoise(workspaceId, change.id, !change.is_noise);
      setChange({ ...change, is_noise: updated.is_noise });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update noise flag");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner />;
  if (error && !change) return <ErrorBox message={error} />;
  if (!change) return <ErrorBox message="Change not found" />;

  return (
    <div>
      <PageHeader
        title="Change detail"
        description={change.ai_summary || change.diff_summary || "Content change"}
        actions={
          <>
            <Button type="button" variant="secondary" disabled={busy} onClick={toggleNoise}>
              {change.is_noise ? "Unmark noise" : "Mark as noise"}
            </Button>
            <Link href={`/monitors/${change.monitor_id}`}>
              <Button type="button" variant="ghost">
                Back to monitor
              </Button>
            </Link>
          </>
        }
      />
      {error ? <ErrorBox message={error} /> : null}

      <div className="mb-5 flex flex-wrap gap-2">
        {change.change_category ? <Badge tone="info">{change.change_category}</Badge> : null}
        {change.is_noise ? <Badge tone="warn">noise</Badge> : <Badge tone="success">signal</Badge>}
      </div>

      {change.ai_summary ? (
        <Card className="mb-4">
          <p className="section-label">AI summary</p>
          <p className="mt-2.5 text-sm leading-relaxed text-slate-800 dark:text-slate-200">{change.ai_summary}</p>
        </Card>
      ) : null}

      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <Card className="!p-4">
          <p className="section-label">Previous hash</p>
          <p className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">
            {change.previous_hash ?? "—"}
          </p>
        </Card>
        <Card className="!p-4">
          <p className="section-label">New hash</p>
          <p className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">{change.new_hash}</p>
        </Card>
      </div>

      {(change.previous_text || change.new_text) && (
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          <div>
            <SectionTitle>Before</SectionTitle>
            <ReadableContent
              text={change.previous_text || ""}
              maxChars={4000}
              emptyLabel="No previous text."
            />
          </div>
          <div>
            <SectionTitle>After</SectionTitle>
            <ReadableContent
              text={change.new_text || ""}
              maxChars={4000}
              emptyLabel="No new text."
            />
          </div>
        </div>
      )}

      <SectionTitle>Line diff</SectionTitle>
      <Card className="!p-0 overflow-hidden">
        <div className="max-h-[min(70vh,32rem)] overflow-auto">
          {change.diff ? (
            <pre className="diff m-0 whitespace-pre-wrap break-words p-4 font-mono text-[13px] leading-6">
              {change.diff}
            </pre>
          ) : (
            <p className="p-4 text-sm text-slate-500">No diff available.</p>
          )}
        </div>
      </Card>
    </div>
  );
}
