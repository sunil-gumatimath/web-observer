"use client";

import { useState } from "react";

export function VisualDiff({ before, after, alt = "screenshot" }: { before?: string | null; after?: string | null; alt?: string }) {
  const [pos, setPos] = useState(50);
  if (!before || !after) {
    return (
      <div className="rounded-xl border bg-slate-50 dark:bg-slate-800 p-4 text-center text-sm text-muted">
        Screenshots will appear here once visual monitoring captures both states.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded-xl border select-none" style={{ height: 360 }}>
        <img src={after} alt={alt + " after"} className="absolute inset-0 h-full w-full object-contain bg-white" />
        <div className="absolute inset-0 overflow-hidden" style={{ width: `${pos}%` }}>
          <img src={before} alt={alt + " before"} className="h-full w-full object-contain bg-white" style={{ width: `${100 / (pos / 100)}%`, maxWidth: "none" }} />
        </div>
        <div className="absolute top-0 bottom-0 w-0.5 bg-sky-500" style={{ left: `${pos}%` }} />
        <input
          type="range"
          min={0}
          max={100}
          value={pos}
          onChange={(e) => setPos(Number(e.target.value))}
          className="absolute bottom-2 left-1/2 -translate-x-1/2 w-1/2"
        />
        <span className="absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">before</span>
        <span className="absolute top-2 right-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">after</span>
      </div>
      <div className="flex gap-2 text-xs">
        <span className="rounded border px-2 py-1">Drag slider to compare</span>
        <button onClick={() => setPos(0)} className="rounded border px-2 py-1 hover:bg-slate-50">Show after</button>
        <button onClick={() => setPos(100)} className="rounded border px-2 py-1 hover:bg-slate-50">Show before</button>
        <button onClick={() => setPos(50)} className="rounded border px-2 py-1 hover:bg-slate-50">Split</button>
      </div>
    </div>
  );
}
