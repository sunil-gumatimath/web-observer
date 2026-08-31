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
  | { type: "table"; rows: string[][] }
  | { type: "image"; alt: string; src: string };

function isTableChunk(chunk: string): boolean {
  const lines = chunk.split("\n").filter((l) => l.trim().length > 0);
  const pipeLines = lines.filter((l) => l.trim().startsWith("|")).length;
  // HN tables have no separator, so just need mostly pipe lines
  return pipeLines >= 2 && pipeLines / lines.length >= 0.6;
}

function parseTable(chunk: string): string[][] {
  const rows: string[][] = [];
  for (const line of chunk.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|")) continue;
    if (/^\|\s*[-:| ]+\s*\|/.test(t)) continue; // separator
    const cells = t
      .slice(1, t.endsWith("|") ? -1 : undefined)
      .split("|")
      .map((c) => c.trim());
    rows.push(cells);
  }
  return rows;
}

function cleanCell(cell: string): string {
  // keep markdown links as text: [title](url) -> title
  return cell.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/\s+/g, " ").trim();
}

const NAV_TERMS = new Set([
  "research",
  "products",
  "business",
  "developers",
  "company",
  "foundation",
  "skip to main content",
  "try chatgpt",
  "log in",
  "login",
  "all",
  "filter",
  "sort",
]);

function isNavBlock(lines: string[]): boolean {
  if (lines.length < 3 || lines.length > 12) return false;
  const norm = lines.map((l) => l.toLowerCase().replace(/\[([^\]]+)\].*/, "$1").replace(/[^a-z ]/g, "").trim());
  const navCount = norm.filter((t) => NAV_TERMS.has(t) || t.length <= 2).length;
  return navCount / lines.length >= 0.6;
}

function toBlocks(text: string, baseUrl?: string): Block[] {
  const chunks = text.split(/\n{2,}/).map((c) => c.trim()).filter(Boolean);
  const blocks: Block[] = [];

  for (const chunk of chunks) {
    // skip pure nav chrome chunks
    const prelimLines = chunk.split("\n").map((l) => l.trim()).filter(Boolean);
    if (isNavBlock(prelimLines)) continue;
    if (isTableChunk(chunk)) {
      const rows = parseTable(chunk);
      if (rows.length) {
        // HN-style 2-row-per-story table: collapse pairs into single story rows
        const isHN = rows.some((r) => r.join(" ").includes("points by"));
        if (isHN) {
          const stories: string[][] = [];
          for (let i = 0; i < rows.length; i += 2) {
            const a = rows[i] ?? [];
            const b = rows[i + 1] ?? [];
            const titleRaw = (a.join(" | ") || "").trim();
            const metaRaw = (b.join(" | ") || "").trim();
            const title = cleanCell(titleRaw).replace(/^\d+\.\s*/, "").trim();
            const meta = cleanCell(metaRaw).trim();
            if (title) stories.push([title || cleanCell(a.join(" ")) , meta]);
            else if (titleRaw) stories.push([cleanCell(titleRaw), meta]);
          }
          if (stories.length) {
            blocks.push({ type: "table", rows: stories });
            continue;
          }
        }
        // generic: clean each cell and join non-empty with " · "
        const cleaned = rows.map((r) => r.map(cleanCell).filter(Boolean).join(" · ")).filter(Boolean).map((s) => [s]);
        if (cleaned.length) {
          blocks.push({ type: "table", rows: cleaned });
          continue;
        }
        blocks.push({ type: "table", rows });
        continue;
      }
    }
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
}: {
  text: string;
  maxChars?: number;
  title?: string;
  emptyLabel?: string;
  baseUrl?: string;
  aiChangeSummary?: string | null;
  changeCategory?: string | null;
  isNoise?: boolean | null;
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
            {wordCount.toLocaleString()} words · ~{Math.max(1, Math.ceil(wordCount / 200))} min read
            {needsTruncate && !expanded ? ` · preview of ${maxChars.toLocaleString()} chars` : expanded ? " · full text" : ""}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
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

      {/* AI Change Summary Banner — webdog parity: only change summaries */}
      {aiChangeSummary ? (
        <div className="border-b border-[var(--border)] bg-gradient-to-r from-sky-500/10 via-indigo-500/5 to-transparent px-5 py-3.5 dark:from-sky-950/30 dark:via-indigo-950/15">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sky-700 dark:text-sky-400">
            <span className="inline-flex items-center gap-1.5 font-bold">
              <svg className="h-3.5 w-3.5 text-sky-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z"/>
              </svg>
              AI Change Summary
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
            {aiChangeSummary}
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
            ) : block.type === "table" ? (
              <div key={i} className="space-y-2">
                {block.rows.map((row, j) => (
                  <div
                    key={j}
                    className="flex gap-3 rounded-lg border border-[var(--border)] bg-slate-50/60 px-3 py-2.5 dark:bg-slate-900/30"
                  >
                    <span className="shrink-0 text-xs font-mono font-semibold text-slate-500">{j + 1}.</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium leading-snug text-slate-900 dark:text-slate-100">{row[0]}</p>
                      {row[1] ? <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{row[1]}</p> : null}
                    </div>
                  </div>
                ))}
              </div>
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
