"use client";

import { useCallback, useRef, useState, type PointerEvent } from "react";
import { Button } from "./ui";

export function VisualDiff({
  before,
  after,
  alt = "screenshot",
  beforeCaption,
  afterCaption,
}: {
  before?: string | null;
  after?: string | null;
  alt?: string;
  beforeCaption?: string | null;
  afterCaption?: string | null;
}) {
  const [pos, setPos] = useState(50);
  // The src that failed to load, if any. Storing the URL (not the side) means
  // a new comparison clears the failure automatically.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  // Screenshots can be captured *after* the change row appears (alert
  // screenshots run on the browser queue), so a 404 is often temporary.
  // Retrying with a cache-busting query re-attempts the load.
  const [attempt, setAttempt] = useState(0);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);

  const updateFromClientX = useCallback((clientX: number) => {
    const el = trackRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0) return;
    const next = ((clientX - rect.left) / rect.width) * 100;
    setPos(Math.min(100, Math.max(0, next)));
  }, []);

  const handlePointerDown = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      // Let the native range/buttons handle their own gestures.
      const target = e.target as HTMLElement | null;
      if (target?.closest("input,button,a")) return;
      if (e.pointerType === "mouse" && e.button !== 0) return;
      draggingRef.current = true;
      e.currentTarget.setPointerCapture?.(e.pointerId);
      updateFromClientX(e.clientX);
    },
    [updateFromClientX],
  );

  const handlePointerMove = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (!draggingRef.current) return;
      updateFromClientX(e.clientX);
    },
    [updateFromClientX],
  );

  const endDrag = useCallback(() => {
    draggingRef.current = false;
  }, []);

  const retry = useCallback(() => {
    setFailedSrc(null);
    setAttempt((n) => n + 1);
  }, []);

  const withAttempt = useCallback(
    (url: string) => (attempt > 0 ? `${url}${url.includes("?") ? "&" : "?"}retry=${attempt}` : url),
    [attempt],
  );

  // An image that failed before hydration never fires onError. Checking the
  // element on mount closes that gap — screenshots are captured best-effort,
  // so a 404 is a normal state, not an edge case.
  const checkImg = (src: string) => (el: HTMLImageElement | null) => {
    if (el && el.complete && el.naturalWidth === 0) setFailedSrc(src);
  };

  if (!before || !after) {
    return (
      <div className="rounded-[12px] border border-[var(--hairline)] bg-[var(--surface-1)] p-4 text-center text-xs text-[var(--muted)]">
        Screenshots will appear here once visual monitoring captures both states.
      </div>
    );
  }

  // Screenshots are captured best-effort, so a missing file is normal — never
  // render a broken half-image comparison.
  const failedSide = failedSrc === after ? "after" : failedSrc === before ? "before" : null;
  if (failedSide) {
    return (
      <div className="rounded-[12px] border border-[var(--hairline)] bg-[var(--surface-1)] p-4 text-center text-xs text-[var(--muted)]">
        <p>
          The {failedSide} screenshot for this comparison is unavailable — the capture may have failed
          or not finished yet.
        </p>
        <Button type="button" variant="secondary" size="sm" onClick={retry} className="mt-2">
          Retry
        </Button>
      </div>
    );
  }

  const clamped = Math.min(100, Math.max(0, pos));
  const showBeforeLabel = clamped > 12;
  const showAfterLabel = clamped < 88;

  return (
    <div className="space-y-2">
      <div
        role="group"
        aria-label="Before and after image comparison"
        className="relative overflow-hidden rounded-[12px] border border-[var(--hairline)] bg-[var(--surface-1)]"
      >
        <div
          ref={trackRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          // Full-page captures are tall: scroll inside the frame instead of
          // shrinking the whole page into a few hundred pixels.
          className="relative max-h-[min(65vh,520px)] cursor-ew-resize touch-pan-y select-none overflow-x-hidden overflow-y-auto"
        >
          {/* Both images are laid out at the same width so they share one
              scale — with object-contain, two captures of different heights
              were letterboxed differently and the wipe compared off-by-N
              pixels. object-* alignment is now purely top/left. */}
          <div className="relative w-full">
            <img
              src={withAttempt(after)}
              alt={`${alt} after`}
              draggable={false}
              ref={checkImg(after)}
              onError={() => setFailedSrc(after)}
              className="block h-auto w-full"
            />
            <div
              aria-hidden
              className="absolute inset-0"
              style={{ clipPath: `inset(0 ${100 - clamped}% 0 0)` }}
            >
              <img
                src={withAttempt(before)}
                alt=""
                draggable={false}
                ref={checkImg(before)}
                onError={() => setFailedSrc(before)}
                className="block h-auto w-full"
              />
            </div>

            <div
              aria-hidden
              className="pointer-events-none absolute inset-y-0"
              style={{ left: `${clamped}%` }}
            >
              <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-[var(--primary)]" />
            </div>
          </div>
        </div>

        {/* Viewport-fixed overlay: labels and handle stay visible while the
            capture scrolls. */}
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <span
            className={`absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white transition-opacity ${showBeforeLabel ? "opacity-100" : "opacity-0"}`}
          >
            Before
          </span>
          <span
            className={`absolute top-2 right-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white transition-opacity ${showAfterLabel ? "opacity-100" : "opacity-0"}`}
          >
            After
          </span>
          <div
            className="absolute top-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-[var(--hairline-strong)] bg-[var(--surface-2)] text-xs font-semibold text-[var(--fg)]"
            style={{ left: `${clamped}%` }}
          >
            &#8596;
          </div>
        </div>

        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={Math.round(clamped)}
          onChange={(e) => setPos(Math.min(100, Math.max(0, Number(e.target.value))))}
          aria-label="Comparison position"
          aria-valuetext={`${Math.round(clamped)} percent before`}
          className="absolute bottom-2 left-1/2 w-1/2 -translate-x-1/2 accent-[var(--primary)]"
        />
      </div>
      {beforeCaption || afterCaption ? (
        <div className="flex flex-wrap justify-between gap-2 px-1 text-xs text-[var(--ink-subtle)]">
          <span>Before{beforeCaption ? ` · ${beforeCaption}` : ""}</span>
          <span>After{afterCaption ? ` · ${afterCaption}` : ""}</span>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="px-1 text-[var(--muted)]">
          Drag on the image or use arrow keys to compare
        </span>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => setPos(0)}
          aria-pressed={clamped === 0}
        >
          Show after
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => setPos(100)}
          aria-pressed={clamped === 100}
        >
          Show before
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => setPos(50)}
          aria-pressed={clamped === 50}
        >
          Split
        </Button>
      </div>
    </div>
  );
}
