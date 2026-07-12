"use client";

import { useState, type FormEvent } from "react";
import {
  Button,
  Card,
  ErrorBox,
  Label,
  PageHeader,
  SuccessBox,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

export default function ImportPage() {
  usePageTitle("Bulk import");
  const [csvText, setCsvText] = useState(
    "name,url,mode,schedule_interval_minutes\nExample,https://example.com/,whole_page,60\n",
  );
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const ws = await ensureWorkspace();
      const body = await api.bulkImportMonitors(ws, csvText);
      setResult(
        `Created ${body.created_count}. Skipped ${body.skipped?.length ?? 0}. Errors ${body.errors?.length ?? 0}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Bulk import"
        description="Import monitors from CSV (name, url, mode, schedule_interval_minutes)."
      />
      {error ? <ErrorBox message={error} /> : null}
      {result ? <SuccessBox message={result} /> : null}
      <Card className="max-w-3xl">
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <Label htmlFor="csv">CSV</Label>
            <Textarea
              id="csv"
              className="h-64 font-mono text-xs"
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={busy}>
            {busy ? "Importing…" : "Import monitors"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
