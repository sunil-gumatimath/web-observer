"use client";

import { cn } from "./ui";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div suppressHydrationWarning className={cn("animate-pulse rounded-[4px] bg-[var(--surface-2)]", className)} {...props} />;
}

export function SkeletonCard() {
  return (
    <div suppressHydrationWarning className="glass-card !p-4 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div suppressHydrationWarning className="surface overflow-hidden">
      <div suppressHydrationWarning className="h-10 border-b border-[var(--hairline)] bg-[var(--surface-1)] flex gap-4 p-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-20" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} suppressHydrationWarning className="flex gap-4 p-3 border-b border-[var(--hairline)] last:border-0">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-5 w-16" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonStats() {
  return (
    <div suppressHydrationWarning className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} suppressHydrationWarning className="glass-card !p-4 space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-2 w-full" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonHero() {
  return (
    <div suppressHydrationWarning className="rounded-[12px] border border-[var(--hairline)] overflow-hidden bg-[var(--surface-1)]">
      <Skeleton className="h-36 sm:h-44 w-full rounded-none" />
      <div suppressHydrationWarning className="p-4 space-y-3">
        <div suppressHydrationWarning className="flex gap-3">
          <Skeleton className="h-16 w-16 rounded-[8px]" />
          <div suppressHydrationWarning className="space-y-2 flex-1">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-64" />
          </div>
        </div>
      </div>
    </div>
  );
}
