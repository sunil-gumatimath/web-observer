"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/components/ui";

export type ScreenshotStatus = "loading" | "ready" | "missing" | "error";

/** Fetch a screenshot as a blob and expose an object URL (auth-aware). */
export function useScreenshotUrl(workspaceId: string, snapshotId: string) {
  const [url, setUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<ScreenshotStatus>("loading");

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setStatus("loading");
    setUrl(null);
    api
      .fetchScreenshotImage(workspaceId, snapshotId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        setStatus("ready");
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && (e.status === 410 || e.status === 404)) {
          setStatus("missing");
        } else {
          setStatus("error");
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [workspaceId, snapshotId]);

  return { url, status };
}

export function ScreenshotImage({
  workspaceId,
  snapshotId,
  alt,
  className,
  imgClassName,
}: {
  workspaceId: string;
  snapshotId: string;
  alt?: string;
  className?: string;
  imgClassName?: string;
}) {
  const { url, status } = useScreenshotUrl(workspaceId, snapshotId);

  if (status === "loading") {
    return (
      <div className={cn("flex items-center justify-center", className)}>
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-sky-500/20 border-t-sky-500" />
      </div>
    );
  }

  if (status === "missing") {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-1.5 px-3 text-center text-xs text-slate-500 dark:text-slate-400",
          className,
        )}
      >
        <svg
          className="h-7 w-7 opacity-60"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3 17.25V9a2.25 2.25 0 0 1 2.25-2.25h12A2.25 2.25 0 0 1 19.5 9v8.25m-9-7.5h.008v.008H10.5v-.008Z"
          />
        </svg>
        <span>Screenshot unavailable</span>
      </div>
    );
  }

  if (status === "error" || !url) {
    return (
      <div
        className={cn(
          "flex items-center justify-center px-3 text-center text-xs text-rose-600 dark:text-rose-300",
          className,
        )}
      >
        Couldn’t load image
      </div>
    );
  }

  return (
    <img
      src={url}
      alt={alt ?? "Screenshot"}
      className={cn(imgClassName ?? "h-full w-full object-cover")}
      loading="lazy"
    />
  );
}

export type ScreenshotMeta = Array<{ label: string; value: ReactNode }>;

/** Modal lightbox for a single screenshot with optional metadata sidebar. */
export function ScreenshotLightbox({
  workspaceId,
  snapshotId,
  title,
  meta,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  workspaceId: string;
  snapshotId: string | null;
  title: string;
  meta: ScreenshotMeta;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && hasPrev && onPrev) onPrev();
      if (e.key === "ArrowRight" && hasNext && onNext) onNext();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onPrev, onNext, hasPrev, hasNext]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  if (!snapshotId) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-3">
          <h3 className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
            {title}
          </h3>
          <div className="flex items-center gap-1">
            {hasPrev || hasNext ? (
              <>
                <button
                  type="button"
                  onClick={onPrev}
                  disabled={!hasPrev}
                  aria-label="Previous screenshot"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-200/60 disabled:opacity-30 dark:text-slate-300 dark:hover:bg-white/5"
                >
                  ‹
                </button>
                <button
                  type="button"
                  onClick={onNext}
                  disabled={!hasNext}
                  aria-label="Next screenshot"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-200/60 disabled:opacity-30 dark:text-slate-300 dark:hover:bg-white/5"
                >
                  ›
                </button>
              </>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-white/5"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4 md:flex-row">
          <div className="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-[var(--border)] bg-slate-900/40 p-2">
            <ScreenshotImage
              workspaceId={workspaceId}
              snapshotId={snapshotId}
              alt={title}
              className="flex h-full w-full items-center justify-center"
              imgClassName="max-h-[70vh] w-auto object-contain"
            />
          </div>
          {meta.length > 0 ? (
            <div className="md:w-64 md:shrink-0">
              <dl className="space-y-2">
                {meta.map((m) => (
                  <div
                    key={m.label}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface-bg)] px-3 py-2"
                  >
                    <dt className="section-label">{m.label}</dt>
                    <dd className="mt-1 text-sm text-slate-800 dark:text-slate-200">{m.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
