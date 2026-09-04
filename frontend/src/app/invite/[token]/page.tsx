"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button, Card } from "@/components/ui";
import { api, type MeResponse } from "@/lib/api";
import { setStoredWorkspaceId } from "@/lib/workspace";
import type { InvitePreview } from "@/lib/types";

export default function InvitePage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? "";
  const router = useRouter();
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .previewInvite(token)
      .then(setPreview)
      .catch((e) => setError(e instanceof Error ? e.message : "Invite link is not available."));
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));
  }, [token]);

  async function redeem() {
    setWorking(true);
    setError(null);
    try {
      const r = await api.redeemInvite(token);
      setDone(r.message);
      setStoredWorkspaceId(r.workspace_id);
      setTimeout(() => router.push("/dashboard"), 900);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not accept invite.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-md px-4">
      <Link href="/" className="text-sm font-semibold tracking-tight text-[var(--accent)] hover:opacity-80">
        Web Observer
      </Link>

      {done ? (
        <Card className="mt-6 space-y-3 border-emerald-500/40">
          <p className="text-sm text-emerald-700 dark:text-emerald-300">✓ {done}</p>
          <p className="text-xs text-slate-500">Taking you to your dashboard…</p>
        </Card>
      ) : (
        <Card className="mt-6 space-y-4">
          <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
            {error ? "Invite unavailable" : `Join ${preview?.workspace_name ?? "this workspace"}?`}
          </h1>
          {error ? (
            <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>
          ) : !preview ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : (
            <>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                You&apos;ll be added as <span className="font-medium">{preview.role}</span>.
              </p>
              {!me ? (
                <p className="text-xs text-slate-500">
                  You&apos;ll need to{" "}
                  <Link
                    className="text-[var(--accent)] underline"
                    href={`/sign-in?redirect_url=/invite/${encodeURIComponent(token)}`}
                  >
                    sign in
                  </Link>{" "}
                  first.
                </p>
              ) : null}
              <Button type="button" disabled={working} onClick={redeem} className="w-full">
                {working ? "Accepting…" : "Accept invite"}
              </Button>
            </>
          )}
        </Card>
      )}
    </div>
  );
}