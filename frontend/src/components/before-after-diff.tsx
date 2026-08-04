"use client";

import { useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui";

/**
 * Word-level before/after diff.
 *
 * Tokenizes both texts (words + newlines), runs an LCS over the tokens, then
 * renders each side with the changed words highlighted inline — removed words
 * are struck through in the "Before" panel, added words are highlighted in the
 * "After" panel, so readers never have to scan the whole page to spot what
 * actually changed.
 */

type Tok = { type: "word" | "nl"; value: string };
type Marked = { tok: Tok; mark: "same" | "add" | "del" };

function tokenize(text: string): Tok[] {
  const out: Tok[] = [];
  const re = /\n+|\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const v = m[0];
    out.push(v.startsWith("\n") ? { type: "nl", value: v } : { type: "word", value: v });
  }
  return out;
}

function lcsOps(
  a: Tok[],
  b: Tok[],
): Array<{ type: "eq" | "del" | "add"; i: number; j: number }> {
  const n = a.length;
  const m = b.length;
  const dp: Uint32Array[] = [];
  for (let i = 0; i <= n; i++) dp.push(new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] =
        a[i].value === b[j].value
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops: Array<{ type: "eq" | "del" | "add"; i: number; j: number }> = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i].value === b[j].value) {
      ops.push({ type: "eq", i, j });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: "del", i, j });
      i++;
    } else {
      ops.push({ type: "add", i, j });
      j++;
    }
  }
  while (i < n) {
    ops.push({ type: "del", i, j });
    i++;
  }
  while (j < m) {
    ops.push({ type: "add", i, j });
    j++;
  }
  return ops;
}

function diffTokens(before: string, after: string): { before: Marked[]; after: Marked[] } {
  const a = tokenize(before);
  const b = tokenize(after);
  const beforeMarked: Marked[] = [];
  const afterMarked: Marked[] = [];
  for (const op of lcsOps(a, b)) {
    if (op.type === "eq") {
      beforeMarked.push({ tok: a[op.i], mark: "same" });
      afterMarked.push({ tok: b[op.j], mark: "same" });
    } else if (op.type === "del") {
      beforeMarked.push({ tok: a[op.i], mark: "del" });
    } else {
      afterMarked.push({ tok: b[op.j], mark: "add" });
    }
  }
  return { before: beforeMarked, after: afterMarked };
}

function renderTokens(marked: Marked[], prefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let key = 0;
  for (let idx = 0; idx < marked.length; idx++) {
    const { tok, mark } = marked[idx];
    if (tok.type === "nl") {
      nodes.push(<br key={`${prefix}-br-${key++}`} />);
      continue;
    }
    if (mark === "same") {
      nodes.push(tok.value);
    } else {
      nodes.push(
        <mark
          key={`${prefix}-mark-${key++}`}
          className={mark === "add" ? "hl-add" : "hl-del"}
        >
          {tok.value}
        </mark>,
      );
    }
    if (idx + 1 < marked.length && marked[idx + 1].tok.type !== "nl") {
      nodes.push(" ");
    }
  }
  return nodes;
}

function truncateMarked(marked: Marked[], maxChars: number): Marked[] {
  let count = 0;
  const out: Marked[] = [];
  for (const item of marked) {
    if (item.tok.type === "nl") {
      out.push(item);
      continue;
    }
    if (count + item.tok.value.length > maxChars) break;
    out.push(item);
    count += item.tok.value.length;
  }
  return out;
}

function wordCount(marked: Marked[]): number {
  return marked.filter((x) => x.tok.type === "word").length;
}

function DiffPanel({
  title,
  marked,
  color,
  emptyLabel,
}: {
  title: string;
  marked: Marked[];
  color: "add" | "del";
  emptyLabel: string;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-white shadow-sm dark:bg-slate-950/40">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] bg-slate-50/80 px-4 py-2.5 dark:bg-slate-900/50">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            {title}
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-500">
            {wordCount(marked).toLocaleString()} words
          </p>
        </div>
        <span
          className={`rounded px-2 py-0.5 text-[11px] font-medium ${
            color === "add"
              ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              : "bg-rose-500/10 text-rose-700 dark:text-rose-300"
          }`}
        >
          {color === "add" ? "highlighted = added" : "struck through = removed"}
        </span>
      </div>
      <div className="max-h-[min(70vh,32rem)] overflow-y-auto px-5 py-4">
        {marked.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">{emptyLabel}</p>
        ) : (
          <p className="whitespace-pre-wrap break-words text-[15px] leading-7 text-slate-800 dark:text-slate-200">
            {renderTokens(marked, color)}
          </p>
        )}
      </div>
    </div>
  );
}

export function BeforeAfterDiff({
  before,
  after,
  maxChars = 4000,
}: {
  before: string | null;
  after: string | null;
  maxChars?: number;
}) {
  const { before: bMarked, after: aMarked } = useMemo(
    () => diffTokens(before || "", after || ""),
    [before, after],
  );
  const needsTruncate =
    (before || "").length > maxChars || (after || "").length > maxChars;
  const [expanded, setExpanded] = useState(false);

  const bDisplay = expanded ? bMarked : truncateMarked(bMarked, maxChars);
  const aDisplay = expanded ? aMarked : truncateMarked(aMarked, maxChars);

  const hasContent = Boolean(before || after);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Highlighted words show exactly what changed.
        </p>
        {needsTruncate ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Show less" : "Show full text"}
          </Button>
        ) : null}
      </div>
      {hasContent ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <DiffPanel
            title="Before"
            color="del"
            marked={bDisplay}
            emptyLabel="No previous text."
          />
          <DiffPanel
            title="After"
            color="add"
            marked={aDisplay}
            emptyLabel="No new text."
          />
        </div>
      ) : (
        <p className="text-sm text-slate-500 dark:text-slate-400">No text content.</p>
      )}
    </div>
  );
}
