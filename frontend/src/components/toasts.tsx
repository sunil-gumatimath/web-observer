"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cn } from "@/components/ui";

export type ToastTone = "success" | "error" | "info";

export type ToastItem = {
  id: number;
  title: string;
  body?: string;
  tone: ToastTone;
};

type ToastContextValue = {
  push: (t: Omit<ToastItem, "id">) => void;
  success: (title: string, body?: string) => void;
  error: (title: string, body?: string) => void;
  info: (title: string, body?: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 4200;

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (ctx) return ctx;
  // Safe no-op outside provider (e.g. static prerender) so callers never crash.
  const noop = () => {};
  return { push: noop, success: noop, error: noop, info: noop };
}

const toneStyles: Record<ToastTone, string> = {
  success:
    "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-200",
  error: "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-200",
  info: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-200",
};

const toneDot: Record<ToastTone, string> = {
  success: "bg-emerald-500",
  error: "bg-rose-500",
  info: "bg-sky-500",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(1);

  const push = useCallback((t: Omit<ToastItem, "id">) => {
    const id = idRef.current++;
    setToasts((prev) => [...prev.slice(-3), { ...t, id }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, AUTO_DISMISS_MS);
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (title, body) => push({ title, body, tone: "success" }),
      error: (title, body) => push({ title, body, tone: "error" }),
      info: (title, body) => push({ title, body, tone: "info" }),
    }),
    [push],
  );

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((x) => x.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(92vw,380px)] flex-col gap-2"
        suppressHydrationWarning
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "pointer-events-auto flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-sm shadow-lg backdrop-blur-xl animate-fade-in-up",
              "bg-[var(--bg-elevated)]",
              toneStyles[t.tone],
            )}
          >
            <span
              className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", toneDot[t.tone])}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <p className="font-medium leading-snug text-[var(--text)]">{t.title}</p>
              {t.body ? (
                <p className="mt-0.5 break-words text-xs leading-relaxed text-[var(--muted)]">
                  {t.body}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss notification"
              className="shrink-0 rounded-md px-1.5 py-0.5 text-xs text-[var(--muted)] hover:bg-[var(--nav-active-bg)] hover:text-[var(--text)]"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
