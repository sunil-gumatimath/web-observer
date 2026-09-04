"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Badge, Card, SectionTitle } from "@/components/ui";
import { api, brandAssetUrl } from "@/lib/api";
import type { PublicShare } from "@/lib/types";

export default function PublicSharePage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? "";
  const [data, setData] = useState<PublicShare | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .getPublicShare(token)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Share link is not available."));
  }, [token]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Link unavailable</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{error}</p>
        <Link href="/" className="mt-6 inline-block text-sm text-[var(--accent)] hover:opacity-80">
          Web Observer
        </Link>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center text-sm text-slate-500">Loading…</div>
    );
  }

  const logo = brandAssetUrl(data.monitor.brand?.logo_path);
  const hero = brandAssetUrl(data.monitor.brand?.hero_path);

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <Link href="/" className="text-sm font-semibold tracking-tight text-[var(--accent)] hover:opacity-80">
        Web Observer
      </Link>

      <div className="mt-6 flex items-start gap-4 rounded-2xl border border-[var(--border)] bg-white/70 p-5 dark:bg-slate-950/40">
        {logo ? (
          <img src={logo} alt="" className="h-12 w-12 rounded-xl object-contain" />
        ) : (
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--fg)] text-lg font-bold text-white">
            {data.monitor.name?.slice(0, 1) || "W"}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-semibold text-slate-900 dark:text-white">
            {data.monitor.name}
          </h1>
          <a
            href={data.monitor.url}
            target="_blank"
            rel="noreferrer"
            className="mt-0.5 block truncate text-sm text-[var(--accent)] hover:opacity-80"
          >
            {data.monitor.url}
          </a>
          {data.monitor.watch_note ? (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Watching: {data.monitor.watch_note}
            </p>
          ) : null}
        </div>
        <Badge tone="neutral">{data.monitor.mode}</Badge>
      </div>

      {hero ? (
        <img src={hero} alt={`${data.monitor.name} screenshot`} className="mt-5 w-full rounded-2xl border border-[var(--border)]" />
      ) : null}
      {/* Gap: PublicShare exposes no screenshot URLs or run ids, so the
          VisualDiff slider cannot mount here. Screenshot blobs are reachable
          via the public asset endpoint only with a known object key
          (screenshots/{monitor_id}/{run_id}.png), which the public share
          payload does not include. Keep this page auth-free: summaries only. */}
      <div className="mt-8">
        <SectionTitle>Visual comparison</SectionTitle>
        <Card className="text-sm text-slate-500 dark:text-slate-400">
          Screenshot comparisons are available in the app. This public link shares change summaries only.
        </Card>
      </div>

      <div className="mt-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Changes ({data.total})
        </h2>
        {data.alerts.length === 0 ? (
          <Card className="text-sm text-slate-500 dark:text-slate-400">
            No changes detected yet.
          </Card>
        ) : (
          <div className="space-y-3">
            {data.alerts.map((a) => (
              <Card key={a.id} className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Badge tone={a.change_category ? "warn" : "neutral"}>
                    {a.change_category || "change"}
                  </Badge>
                  <span className="text-xs text-slate-500">
                    {new Date(a.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="text-sm text-slate-800 dark:text-slate-100">
                  {a.ai_summary || a.diff_summary || "Content changed."}
                </p>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}