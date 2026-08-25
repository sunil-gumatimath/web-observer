"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui";

/** Soft-clean extracted page text for human reading. */
export function prepareReadableText(raw: string): string {
  let t = raw.replace(/\u00a0/g, " ").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  // collapse runs of spaces/tabs on each line
  t = t
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .join("\n");
  // collapse 3+ blank lines
  t = t.replace(/\n{3,}/g, "\n\n").trim();
  return t;
}

type Block =
  | { type: "paragraph"; lines: string[] }
  | { type: "list"; items: string[] };

function toBlocks(text: string): Block[] {
  const chunks = text.split(/\n{2,}/).map((c) => c.trim()).filter(Boolean);
  const blocks: Block[] = [];

  for (const chunk of chunks) {
    const lines = chunk.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) continue;

    // Many short lines → bullet list (nav / headlines / list_items mode)
    const shortCount = lines.filter((l) => l.length <= 80).length;
    if (lines.length >= 3 && shortCount / lines.length >= 0.7) {
      blocks.push({ type: "list", items: lines });
    } else if (lines.length === 1) {
      blocks.push({ type: "paragraph", lines });
    } else {
      // Medium blocks: keep line breaks as soft paragraphs when lines are sentence-like
      const avg = lines.reduce((n, l) => n + l.length, 0) / lines.length;
      if (avg < 60 && lines.length >= 2) {
        blocks.push({ type: "list", items: lines });
      } else {
        blocks.push({ type: "paragraph", lines });
      }
    }
  }
  return blocks;
}

export function ReadableContent({
  text,
  maxChars = 2500,
  title,
  emptyLabel = "No text content.",
}: {
  text: string;
  maxChars?: number;
  title?: string;
  emptyLabel?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const prepared = useMemo(() => prepareReadableText(text || ""), [text]);

  if (!prepared) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">{emptyLabel}</p>;
  }

  const needsTruncate = prepared.length > maxChars;
  const display = expanded || !needsTruncate ? prepared : `${prepared.slice(0, maxChars).trimEnd()}`;
  const blocks = toBlocks(display);
  const wordCount = prepared.split(/\s+/).filter(Boolean).length;
  const lineCount = prepared.split("\n").filter(Boolean).length;

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-white shadow-sm dark:bg-slate-950/40">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] bg-slate-50/80 px-4 py-2.5 dark:bg-slate-900/50">
        <div>
          {title ? (
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              {title}
            </p>
          ) : null}
          <p className="text-[11px] text-slate-500 dark:text-slate-500">
            {wordCount.toLocaleString()} words · {lineCount.toLocaleString()} lines
            {needsTruncate && !expanded ? " · truncated" : ""}
          </p>
        </div>
        {needsTruncate ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Show less" : "Show full text"}
          </Button>
        ) : null}
      </div>

      <div
        className={
          expanded
            ? "max-h-[min(70vh,36rem)] overflow-y-auto px-5 py-4"
            : "max-h-80 overflow-y-auto px-5 py-4"
        }
      >
        <div className="space-y-3.5 text-[15px] leading-7 text-slate-800 dark:text-slate-200">
          {blocks.map((block, i) =>
            block.type === "list" ? (
              <ul key={i} className="list-disc space-y-1.5 pl-5 marker:text-slate-400">
                {block.items.map((item, j) => (
                  <li key={j} className="pl-0.5">
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <p key={i} className="whitespace-pre-wrap break-words">
                {block.lines.join("\n")}
              </p>
            ),
          )}
          {needsTruncate && !expanded ? (
            <p className="pt-1 text-sm italic text-slate-500 dark:text-slate-400">…</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
