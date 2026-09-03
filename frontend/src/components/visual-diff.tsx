"use client";

import { useCallback, useRef, useState, type PointerEvent } from "react";
import { Button } from "./ui";

export function VisualDiff({
  before,
  after,
  alt = "screenshot",
}: {
  before?: string | null;
  after?: string | null;
  alt?: string;
}) {
  const [pos, setPos] = useState(50);
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

  if (!before || !after) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-bg)] p-4 text-center text-sm text-[var(--muted)]">
        Screenshots will appear here once visual monitoring captures both states.
      </div>
    );
  }

  const clamped = Math.min(100, Math.max(0, pos));
  const showBeforeLabel = clamped > 12;
  const showAfterLabel = clamped < 88;

  return (
    <div className="space-y-2">
      <div
        ref={trackRef}
        role="group"
        aria-label="Before and after image comparison"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className="relative cursor-ew-resize touch-none overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-bg)] select-none"
        style={{ height: 360 }}
      >
        <img
          src={after}
          alt={`${alt} after`}
          draggable={false}
          className="absolute inset-0 h-full w-full bg-white object-contain"
        />
        <div
          aria-hidden
          className="absolute inset-0"
          style={{ clipPath: `inset(0 ${100 - clamped}% 0 0)` }}
        >
          <img
            src={before}
            alt=""
            draggable={false}
            className="absolute inset-0 h-full w-full bg-white object-contain"
          />
        </div>

        <div aria-hidden className="pointer-events-none absolute inset-y-0" style={{ left: `${clamped}%` }}>
          <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-sky-500" />
          <div className="absolute top-1/2 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] text-sm font-bold text-[var(--text)] shadow-md">
            &#8596;
          </div>
        </div>

        <span
          aria-hidden
          className={`pointer-events-none absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white transition-opacity ${showBeforeLabel ? "opacity-100" : "opacity-0"}`}
        >
          Before
        </span>
        <span
          aria-hidden
          className={`pointer-events-none absolute top-2 right-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white transition-opacity ${showAfterLabel ? "opacity-100" : "opacity-0"}`}
        >
          After
        </span>

        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={Math.round(clamped)}
          onChange={(e) => setPos(Math.min(100, Math.max(0, Number(e.target.value))))}
          aria-label="Comparison position"
          aria-valuetext={`${Math.round(clamped)} percent before`}
          className="absolute bottom-2 left-1/2 w-1/2 -translate-x-1/2 accent-sky-500"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="px-1 text-[var(--muted)]">Drag on the image or use arrow keys to compare</span>
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
