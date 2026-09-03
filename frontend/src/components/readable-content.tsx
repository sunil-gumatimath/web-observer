"use client";

import React, { useMemo, useState } from "react";
import { Button } from "@/components/ui";
import { resolveImageUrl } from "@/lib/image-md";

/** Decode common HTML entities (named & numeric). */
export function decodeHtmlEntities(str: string): string {
  if (!str) return "";
  return str
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&#(\d+);/g, (_, dec) => String.fromCharCode(parseInt(dec, 10)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

/** Soft-clean extracted page text for human reading. */
export function prepareReadableText(raw: string): string {
  if (!raw) return "";
  let t = raw
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, "")
    // Match img with single, double or unquoted attributes
    .replace(/<img\s+[^>]*src=['"]?([^'"\s>]+)['"]?[^>]*alt=['"]?([^'">]*)['"]?[^>]*\/?>/gi, "![$2]($1)")
    .replace(/<img\s+[^>]*alt=['"]?([^'">]*)['"]?[^>]*src=['"]?([^'"\s>]+)['"]?[^>]*\/?>/gi, "![$1]($2)")
    .replace(/<img\s+[^>]*src=['"]?([^'"\s>]+)['"]?[^>]*\/?>/gi, "![]($1)")
    // Match a with single, double or unquoted href
    .replace(/<a\s+[^>]*href=['"]?([^'"\s>]+)['"]?[^>]*>(.*?)<\/a>/gi, "[$2]($1)")
  t = decodeHtmlEntities(t);
  // Strip known HTML tags while preserving text angle brackets (e.g. <3, ->, 1 < 2)
  t = t.replace(
    /<\/?(?:div|span|p|b|i|strong|em|ul|ol|li|table|tr|td|th|tbody|thead|tfoot|header|footer|nav|section|article|aside|main|br|hr|h[1-6]|form|input|button|label)\b[^>]*>/gi,
    ""
  );
  // collapse excess blank lines
  t = t.replace(/\n{3,}/g, "\n\n").trim();
  return t;
}

/** Render inline markdown tokens (links, bold, italic, code, images). */
export function renderInlineMarkdown(text: string, baseUrl?: string): React.ReactNode[] {
  if (!text) return [];

  // Match: ![alt](url "title"), [text](url "title"), `code`, **bold**, *italic*, __bold__, _italic_
  const pattern = /(!?\[(?:\\.|[^[\]])*\]\((?:\\.|[^()\s]+)(?:\s+["'][^"']*["'])?\)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|__[^_]+__|_[^_]+_)/g;
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIndex = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];

    if (token.startsWith("![")) {
      // Image
      const m = token.match(/^!\[([^\]]*)\]\(([^)\s]+)/);
      if (m) {
        const alt = m[1] || "";
        const src = resolveImageUrl(m[2], baseUrl);
        if (src) {
          nodes.push(
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={`img-${keyIndex++}`}
              src={src}
              alt={alt}
              className="inline-block max-h-6 max-w-24 rounded object-contain align-middle shadow-xs mx-1 border border-slate-200 dark:border-slate-800"
              loading="lazy"
            />
          );
        } else if (alt) {
          nodes.push(alt);
        }
      }
    } else if (token.startsWith("[")) {
      // Link
      const m = token.match(/^\[([^\]]*)\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/);
      if (m) {
        const label = m[1]?.trim() || m[2];
        const href = resolveImageUrl(m[2], baseUrl) || m[2];
        const isSafe = /^https?:\/\//i.test(href) || href.startsWith("/");
        if (isSafe) {
          nodes.push(
            <a
              key={`link-${keyIndex++}`}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sky-600 hover:text-sky-700 hover:underline dark:text-sky-400 dark:hover:text-sky-300 font-medium"
            >
              {renderInlineMarkdown(label, baseUrl)}
            </a>
          );
        } else {
          nodes.push(label);
        }
      }
    } else if (token.startsWith("`") && token.endsWith("`")) {
      nodes.push(
        <code
          key={`code-${keyIndex++}`}
          className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[13px] text-slate-800 dark:bg-slate-800 dark:text-slate-200 border border-slate-200/60 dark:border-slate-700/60"
        >
          {token.slice(1, -1)}
        </code>
      );
    } else if (
      (token.startsWith("**") && token.endsWith("**")) ||
      (token.startsWith("__") && token.endsWith("__"))
    ) {
      // Bold
      nodes.push(
        <strong key={`b-${keyIndex++}`} className="font-semibold text-slate-900 dark:text-slate-100">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (
      (token.startsWith("*") && token.endsWith("*")) ||
      (token.startsWith("_") && token.endsWith("_"))
    ) {
      // Italic
      nodes.push(
        <em key={`em-${keyIndex++}`} className="italic">
          {token.slice(1, -1)}
        </em>
      );
    }

    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "code_block"; lang: string; code: string }
  | { type: "blockquote"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "table"; rows: string[][] }
  | { type: "image"; alt: string; src: string }
  | { type: "paragraph"; text: string };

function cleanTableCell(cell: string): string {
  return cell.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/\s+/g, " ").trim();
}

function parseBlocks(raw: string): Block[] {
  const text = prepareReadableText(raw);
  const lines = text.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i++;
      continue;
    }

    // Code block
    if (trimmed.startsWith("```")) {
      const lang = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing ```
      blocks.push({ type: "code_block", lang, code: codeLines.join("\n") });
      continue;
    }

    // Heading (# ... ######)
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
      });
      i++;
      continue;
    }

    // Blockquote (> ...)
    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      blocks.push({ type: "blockquote", text: quoteLines.join("\n") });
      continue;
    }

    // Markdown Table
    if (trimmed.startsWith("|") && trimmed.endsWith("|") && trimmed.includes("|", 1)) {
      const tableRows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        const rowLine = lines[i].trim();
        // Skip separator rows like |---|---|
        if (!/^\|(?:\s*[:-]+[-| :]*)\|$/.test(rowLine)) {
          const cells = rowLine
            .slice(1, -1)
            .split(/(?<!\\)\|/)
            .map((c) => c.trim().replace(/\\\|/g, "|"));
          if (cells.some((c) => c.length > 0)) {
            tableRows.push(cells);
          }
        }
        i++;
      }

      if (tableRows.length > 0) {
        // HN-style 2-row table check: pair story + metadata
        const isHN = tableRows.some((r) => r.join(" ").includes("points by"));
        if (isHN && tableRows.length >= 2) {
          const stories: string[][] = [];
          for (let k = 0; k < tableRows.length; k += 2) {
            const a = tableRows[k] ?? [];
            const b = tableRows[k + 1] ?? [];
            const titleRaw = (a.join(" | ") || "").trim();
            const metaRaw = (b.join(" | ") || "").trim();
            const title = titleRaw.replace(/^\|\s*\d+\.\s*\|/, "").trim();
            if (title) stories.push([title, metaRaw]);
          }
          if (stories.length) {
            blocks.push({ type: "table", rows: stories });
            continue;
          }
        }
        blocks.push({ type: "table", rows: tableRows });
        continue;
      }
    }

    // Unordered List (- ... or * ... or + ...)
    if (/^[-*+]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*+]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*+]\s+/, ""));
        i++;
      }
      blocks.push({ type: "list", ordered: false, items });
      continue;
    }

    // Ordered List (1. ... 2. ...)
    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i++;
      }
      blocks.push({ type: "list", ordered: true, items });
      continue;
    }

    // Standalone Image: ![alt](src)
    const imgMatch = trimmed.match(/^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)$/);
    if (imgMatch) {
      blocks.push({ type: "image", alt: imgMatch[1], src: imgMatch[2] });
      i++;
      continue;
    }

    // Regular Paragraph: accumulate lines until next block starter or empty line
    const paraLines: string[] = [trimmed];
    i++;
    while (i < lines.length) {
      const nextTrimmed = lines[i].trim();
      if (!nextTrimmed) break;
      if (
        nextTrimmed.startsWith("#") ||
        nextTrimmed.startsWith("```") ||
        nextTrimmed.startsWith(">") ||
        (nextTrimmed.startsWith("|") && nextTrimmed.endsWith("|")) ||
        /^[-*+]\s+/.test(nextTrimmed) ||
        /^\d+\.\s+/.test(nextTrimmed) ||
        /^!\[([^\]]*)\]\(([^)\s]+)/.test(nextTrimmed)
      ) {
        break;
      }
      paraLines.push(nextTrimmed);
      i++;
    }
    blocks.push({ type: "paragraph", text: paraLines.join("\n") });
  }

  return blocks;
}

export function ReadableContent({
  text,
  maxChars = 25000,
  title,
  emptyLabel = "No text content.",
  baseUrl,
}: {
  text: string;
  maxChars?: number;
  title?: string;
  emptyLabel?: string;
  baseUrl?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState<"formatted" | "raw">("formatted");

  const rawText = text || "";
  const prepared = useMemo(() => prepareReadableText(rawText), [rawText]);
  const needsTruncate = prepared.length > maxChars;
  const displayText = expanded || !needsTruncate ? prepared : prepared.slice(0, maxChars).trimEnd();
  const rawDisplayText = expanded || rawText.length <= maxChars ? rawText : rawText.slice(0, maxChars).trimEnd();
  const blocks = useMemo(() => parseBlocks(displayText), [displayText]);
  const wordCount = prepared.split(/\s+/).filter(Boolean).length;

  function handleCopy() {
    const toCopy = viewMode === "raw" ? rawText : prepared;
    if (!toCopy) return;
    navigator.clipboard?.writeText(toCopy).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (!prepared && !rawText) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">{emptyLabel}</p>;
  }

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-white shadow-sm dark:bg-slate-950/40">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] bg-slate-50/90 px-4 py-2.5 dark:bg-slate-900/60">
        <div>
          {title ? (
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              {title}
            </p>
          ) : null}
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            {wordCount.toLocaleString()} words · ~{Math.max(1, Math.ceil(wordCount / 200))} min read
            {needsTruncate && !expanded ? ` · showing first ${maxChars.toLocaleString()} chars` : expanded ? " · full content" : ""}
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          {/* View mode toggle */}
          <div className="flex rounded-lg border border-[var(--border)] bg-slate-100 p-0.5 dark:bg-slate-800 text-xs">
            <button
              type="button"
              onClick={() => setViewMode("formatted")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                viewMode === "formatted"
                  ? "bg-white text-slate-900 shadow-xs dark:bg-slate-700 dark:text-slate-100"
                  : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              Formatted
            </button>
            <button
              type="button"
              onClick={() => setViewMode("raw")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                viewMode === "raw"
                  ? "bg-white text-slate-900 shadow-xs dark:bg-slate-700 dark:text-slate-100"
                  : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              Raw Text
            </button>
          </div>

          <Button type="button" variant="ghost" size="sm" onClick={handleCopy}>
            {copied ? "✓ Copied" : "Copy"}
          </Button>
          {needsTruncate ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Show less" : "Show all"}
            </Button>
          ) : null}
        </div>
      </div>



      {/* Content Body */}
      <div
        className={
          expanded
            ? "max-h-[min(75vh,42rem)] overflow-y-auto px-6 py-5"
            : "max-h-96 overflow-y-auto px-6 py-5"
        }
      >
        {viewMode === "raw" ? (
          <pre className="font-mono text-xs leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-wrap break-words bg-slate-50 dark:bg-slate-900/50 p-4 rounded-lg border border-slate-200 dark:border-slate-800">
            {rawDisplayText}
          </pre>
        ) : (
          <div className="space-y-4 text-[14.5px] leading-relaxed text-slate-800 dark:text-slate-200">
            {blocks.map((block, i) => {
              if (block.type === "heading") {
                const headingClasses =
                  block.level === 1
                    ? "text-xl font-bold tracking-tight text-slate-900 dark:text-slate-50 pt-2 pb-1 border-b border-slate-200/80 dark:border-slate-800"
                    : block.level === 2
                    ? "text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100 pt-1.5"
                    : block.level === 3
                    ? "text-base font-semibold text-slate-900 dark:text-slate-100 pt-1"
                    : "text-sm font-semibold text-slate-900 dark:text-slate-200";

                return (
                  <div key={i} className={headingClasses}>
                    {renderInlineMarkdown(block.text, baseUrl)}
                  </div>
                );
              }

              if (block.type === "code_block") {
                return (
                  <div key={i} className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-900 text-slate-100 shadow-xs">
                    {block.lang ? (
                      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/80 px-3.5 py-1.5 text-[11px] font-mono text-slate-400">
                        <span>{block.lang}</span>
                      </div>
                    ) : null}
                    <pre className="p-4 font-mono text-[12.5px] leading-relaxed overflow-x-auto">
                      <code>{block.code}</code>
                    </pre>
                  </div>
                );
              }

              if (block.type === "blockquote") {
                return (
                  <blockquote
                    key={i}
                    className="border-l-4 border-sky-500 bg-sky-50/50 dark:bg-sky-950/20 py-2.5 px-4 rounded-r-lg text-slate-700 dark:text-slate-300 italic text-[14px] leading-relaxed"
                  >
                    {renderInlineMarkdown(block.text, baseUrl)}
                  </blockquote>
                );
              }

              if (block.type === "list") {
                return block.ordered ? (
                  <ol key={i} className="list-decimal space-y-1.5 pl-6 marker:text-slate-400 marker:font-medium">
                    {block.items.map((item, j) => (
                      <li key={j} className="pl-1">
                        {renderInlineMarkdown(item, baseUrl)}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <ul key={i} className="list-disc space-y-1.5 pl-5 marker:text-sky-500">
                    {block.items.map((item, j) => (
                      <li key={j} className="pl-1">
                        {renderInlineMarkdown(item, baseUrl)}
                      </li>
                    ))}
                  </ul>
                );
              }

              if (block.type === "image") {
                const src = resolveImageUrl(block.src, baseUrl) || block.src;
                return (
                  <figure key={i} className="my-3 overflow-hidden rounded-lg border border-[var(--border)] bg-slate-50/50 dark:bg-slate-900/30 p-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt={block.alt}
                      loading="lazy"
                      className="mx-auto max-h-80 w-auto max-w-full rounded object-contain shadow-xs"
                    />
                    {block.alt ? (
                      <figcaption className="mt-2 text-center text-xs text-slate-500 dark:text-slate-400">
                        {block.alt}
                      </figcaption>
                    ) : null}
                  </figure>
                );
              }

              if (block.type === "table") {
                return (
                  <div key={i} className="my-2 overflow-x-auto rounded-lg border border-[var(--border)]">
                    <table className="w-full text-left text-sm border-collapse">
                      <tbody>
                        {block.rows.map((row, rIdx) => (
                          <tr
                            key={rIdx}
                            className={`border-b border-[var(--border)] last:border-b-0 ${
                              rIdx === 0 && block.rows.length > 1
                                ? "bg-slate-50/90 dark:bg-slate-900/60 font-semibold"
                                : "hover:bg-slate-50/50 dark:hover:bg-slate-900/30"
                            }`}
                          >
                            {row.map((cell, cIdx) => (
                              <td key={cIdx} className="px-3.5 py-2.5 align-top text-[13.5px]">
                                {renderInlineMarkdown(cell, baseUrl)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              }

              // Paragraph
              return (
                <p key={i} className="leading-relaxed whitespace-pre-line">
                  {renderInlineMarkdown(block.text, baseUrl)}
                </p>
              );
            })}

            {needsTruncate && !expanded ? (
              <div className="pt-2 text-center">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setExpanded(true)}
                  className="text-xs"
                >
                  Show remaining {((prepared.length - maxChars) / 1000).toFixed(1)}k characters…
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
