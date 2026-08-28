"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui";
import { extractImages, resolveImageUrl, type MdImage } from "@/lib/image-md";

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
  | { type: "list"; items: string[] }
  | { type: "image"; alt: string; src: string };

function toBlocks(text: string, baseUrl?: string): Block[] {
  const chunks = text.split(/\n{2,}/).map((c) => c.trim()).filter(Boolean);
  const blocks: Block[] = [];

  for (const chunk of chunks) {
    // Images can sit anywhere in a physical line (e.g. a linked logo glued to
    // nav links on one line) — pull them out so they render visually, and
    // keep the remaining text flowing as normal content.
    const chunkImgs: MdImage[] = [];
    const lines: string[] = [];
    for (const rawLine of chunk.split("\n")) {
      const line = rawLine.trim();
      if (!line) continue;
      const ex = extractImages(line);
      chunkImgs.push(...ex.imgs);
      if (ex.rest) lines.push(ex.rest);
    }

    // Many short lines → bullet list (nav / headlines / list_items mode)
    const shortCount = lines.filter((l) => l.length <= 80).length;
    if (lines.length >= 3 && shortCount / lines.length >= 0.7) {
      blocks.push({ type: "list", items: lines });
    } else if (lines.length === 1) {
      blocks.push({ type: "paragraph", lines });
    } else if (lines.length > 1) {
      // Medium blocks: keep line breaks as soft paragraphs when lines are sentence-like
      const avg = lines.reduce((n, l) => n + l.length, 0) / lines.length;
      if (avg < 60 && lines.length >= 2) {
        blocks.push({ type: "list", items: lines });
      } else {
        blocks.push({ type: "paragraph", lines });
      }
    }

    for (const img of chunkImgs) {
      const src = resolveImageUrl(img.src, baseUrl);
      if (src) {
        blocks.push({ type: "image", alt: img.alt, src });
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
  baseUrl,
  aiChangeSummary,
  changeCategory,
  isNoise,
  onSummarizeAi,
  aiSummarizing,
  generatedAiSummary,
}: {
  text: string;
  maxChars?: number;
  title?: string;
  emptyLabel?: string;
  baseUrl?: string;
  aiChangeSummary?: string | null;
  changeCategory?: string | null;
  isNoise?: boolean | null;
  onSummarizeAi?: () => void;
  aiSummarizing?: boolean;
  generatedAiSummary?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const prepared = useMemo(() => prepareReadableText(text || ""), [text]);

  function handleCopy() {
    if (!prepared) return;
    navigator.clipboard?.writeText(prepared).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (!prepared) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">{emptyLabel}</p>;
  }

  const needsTruncate = prepared.length > maxChars;
  const display = expanded || !needsTruncate ? prepared : `${prepared.slice(0, maxChars).trimEnd()}`;
  const blocks = toBlocks(display, baseUrl);
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
        <div className="flex items-center gap-1.5">
          {onSummarizeAi && !aiChangeSummary && !generatedAiSummary ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={aiSummarizing}
              onClick={onSummarizeAi}
              title="Generate AI summary of page content"
            >
              {aiSummarizing ? "✨ Summarizing…" : "✨ AI Summary"}
            </Button>
          ) : null}
          <Button type="button" variant="ghost" size="sm" onClick={handleCopy}>
            {copied ? "✓ Copied" : "Copy"}
          </Button>
          {needsTruncate ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Show less" : "Show full text"}
            </Button>
          ) : null}
        </div>
      </div>

      {/* AI Summary Banner if present */}
      {(aiChangeSummary || generatedAiSummary) ? (
        <div className="border-b border-[var(--border)] bg-gradient-to-r from-sky-500/10 via-indigo-500/5 to-transparent px-5 py-3.5 dark:from-sky-950/30 dark:via-indigo-950/15">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sky-700 dark:text-sky-400">
            <span className="inline-flex items-center gap-1.5 font-bold">
              <svg className="h-3.5 w-3.5 text-sky-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z"/>
              </svg>
              {aiChangeSummary ? "AI Change Summary" : "AI Content Summary"}
            </span>
            {changeCategory ? (
              <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold text-sky-700 dark:bg-sky-500/25 dark:text-sky-300">
                {changeCategory}
              </span>
            ) : null}
            {isNoise ? (
              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-500/25 dark:text-amber-300">
                noise
              </span>
            ) : null}
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-800 dark:text-slate-200">
            {aiChangeSummary || generatedAiSummary}
          </p>
        </div>
      ) : null}

      <div
        className={
          expanded
            ? "max-h-[min(70vh,36rem)] overflow-y-auto px-5 py-4"
            : "max-h-80 overflow-y-auto px-5 py-4"
        }
      >
        <div className="space-y-3.5 text-[15px] leading-7 text-slate-800 dark:text-slate-200">
          {blocks.map((block, i) =>
            block.type === "image" ? (
              <figure key={i} className="overflow-hidden rounded-lg border border-[var(--border)]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={block.src}
                  alt={block.alt}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  className="mx-auto max-h-96 w-auto max-w-full object-contain"
                />
                {block.alt ? (
                  <figcaption className="border-t border-[var(--border)] bg-slate-50/80 px-3 py-1.5 text-xs text-slate-500 dark:bg-slate-900/50 dark:text-slate-400">
                    {block.alt}
                  </figcaption>
                ) : null}
              </figure>
            ) : block.type === "list" ? (
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
