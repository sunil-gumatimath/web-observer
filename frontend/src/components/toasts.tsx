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
  success: "border-[var(--semantic-success)]/30 bg-[var(--semantic-success)]/10 text-[var(--semantic-success)]",
  error: "border-[var(--danger)]/30 bg-[var(--danger)]/10 text-[var(--danger)]",
  info: "border-[var(--primary)]/30 bg-[var(--primary)]/10 text-[var(--primary)]",
};

const toneDot: Record<ToastTone, string> = {
  success: "bg-[var(--semantic-success)]",
  error: "bg-[var(--danger)]",
  info: "bg-[var(--primary)]",
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
              "pointer-events-auto flex items-start gap-2.5 rounded-[8px] border px-3 py-2.5 text-xs backdrop-blur-xl animate-fade-in-up",
              "bg-[var(--surface-1)] border-[var(--hairline-strong)]",
              toneStyles[t.tone],
            )}
          >
            <span
              className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", toneDot[t.tone])}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <p className="font-medium leading-snug text-[var(--fg)]">{t.title}</p>
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
              className="shrink-0 rounded-md px-1.5 py-0.5 text-xs text-[var(--muted)] hover:text-[var(--primary)]"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
