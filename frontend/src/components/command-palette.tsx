"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { clampIndex, filterMonitors, filterRoutes } from "@/lib/palette";
import { ensureWorkspace } from "@/lib/workspace";
import { cn } from "@/components/ui";
import type { Monitor } from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
};

const ROUTES = [
  { href: "/dashboard", label: "Go to Dashboard", hint: "overview" },
  { href: "/monitors", label: "Go to Monitors", hint: "list" },
  { href: "/monitors/new", label: "New monitor", hint: "create" },
  { href: "/changes", label: "Go to Changes", hint: "diffs" },
  { href: "/alerts", label: "Go to Alerts inbox", hint: "inbox" },
  { href: "/import", label: "Go to Import", hint: "bulk csv" },
  { href: "/settings", label: "Go to Settings", hint: "channels billing" },
  { href: "/docs", label: "Go to Docs", hint: "help" },
];

export function CommandPalette({ open, onClose }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Load monitors when the palette opens. Query/active reset happens in the
  // open/close handlers (not here) to avoid cascading renders.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const ws = await ensureWorkspace();
        const list = await api.listMonitors(ws);
        if (!cancelled) setMonitors(list);
      } catch {
        if (!cancelled) setMonitors([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open ]);

  useEffect(() => {
    if (open) {
      const t = window.setTimeout(() => inputRef.current?.focus(), 30);
      return () => window.clearTimeout(t);
    }
  }, [open ]);
  const matchedMonitors = useMemo(
    () => filterMonitors(monitors, query),
    [monitors, query],
  );

  const matchedRoutes = useMemo(() => filterRoutes(ROUTES, query), [query]);

  type Item = { key: string; label: string; sub?: string; run: () => void };
  const items: Item[] = useMemo(
    () => [
      ...matchedRoutes.map((r) => ({
        key: `route:${r.href}`,
        label: r.label,
        sub: r.href,
        run: () => router.push(r.href),
      })),
      ...matchedMonitors.map((m) => ({
        key: `monitor:${m.id}`,
        label: m.name,
        sub: m.url,
        run: () => router.push(`/monitors/${m.id}`),
      })),
    ],
    [matchedRoutes, matchedMonitors, router],
  );

  const close = useCallback(() => {
    setQuery("");
    setActive(0);
    onClose();
  }, [onClose]);

  const go = useCallback(
    (item: Item) => {
      setQuery("");
      setActive(0);
      onClose();
      item.run();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((a) => clampIndex(a + 1, items.length));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => clampIndex(a - 1, items.length));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = items[clampIndex(active, items.length)];
        if (item) go(item);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, items, active, go, close ]);
  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active ]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center bg-black/40 px-4 pt-[12vh] backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-2xl animate-fade-in-up">
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-4">
          <span className="text-sm text-[var(--muted)]" aria-hidden>
            ⌘K
          </span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Jump to monitor, page, or action…"
            aria-label="Search monitors and pages"
            className="h-12 w-full bg-transparent text-sm text-[var(--text)] outline-none placeholder:text-[var(--muted)]"
          />
          <kbd className="rounded border border-[var(--border)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">
            esc
          </kbd>
        </div>
        <div ref={listRef} className="max-h-80 overflow-y-auto p-2">
          {items.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-[var(--muted)]">
              No matches. Try a monitor name, URL, or page.
            </p>
          ) : (
            items.map((item, i) => (
              <button
                key={item.key}
                type="button"
                data-index={i}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(item)}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition",
                  i === active
                    ? "bg-sky-500/15 text-[var(--text)]"
                    : "text-[var(--muted)] hover:bg-[var(--nav-active-bg)]",
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium text-[var(--text)]">
                    {item.label}
                  </span>
                  {item.sub ? (
                    <span className="block truncate text-xs text-[var(--muted)]">
                      {item.sub}
                    </span>
                  ) : null}
                </span>
                <span className="shrink-0 text-xs text-[var(--muted)]">↵</span>
              </button>
            ))
          )}
        </div>
        <div className="flex items-center gap-4 border-t border-[var(--border)] px-4 py-2 text-[11px] text-[var(--muted)]">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span className="ml-auto">{items.length} result{items.length === 1 ? "" : "s"}</span>
        </div>
      </div>
    </div>
  );
}
