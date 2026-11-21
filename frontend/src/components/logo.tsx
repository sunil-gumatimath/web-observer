"use client";

type LogoIconProps = {
  size?: number;
  className?: string;
};

export function LogoIcon({ size = 32, className = "" }: LogoIconProps) {
  return (
    <span
      aria-hidden
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[8px] bg-[var(--surface-1)] border border-[var(--hairline)] ${className}`}
      style={{ width: size, height: size }}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 32 32"
        width={size}
        height={size}
        fill="none"
        role="img"
        aria-label="Web Observer"
        className="h-full w-full"
      >
        <rect x="0.5" y="0.5" width="31" height="31" rx="9" fill="#111827" />
        <rect x="0.5" y="0.5" width="31" height="31" rx="9" stroke="#ffffff" strokeOpacity="0.12" />
        {/* Page outline with a folded corner */}
        <path d="M10 7.5h8l5 5v12H10z" fill="#1f2937" stroke="#e5e7eb" strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M18 7.5v5h5" stroke="#e5e7eb" strokeWidth="1.5" strokeLinejoin="round" />
        {/* Changed-content signal */}
        <path d="M13 20h2.5l1.8-4 2.1 6 1.2-2H23" stroke="#34d399" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

type LogoProps = {
  compact?: boolean;
  iconSize?: number;
  className?: string;
  responsiveWordmark?: boolean;
};

export function Logo({ compact = false, iconSize = 32, className = "", responsiveWordmark = false }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`} aria-label="Web Observer">
      <LogoIcon size={iconSize} />
      {!compact ? (
        <span
          className={`inline-flex items-baseline gap-[0.25em] select-none ${responsiveWordmark ? "hidden sm:inline-flex" : ""}`}
          style={{
            fontFamily:
              'var(--font-display), "Linear Display", "SF Pro Display", Inter, -apple-system, sans-serif',
            letterSpacing: "-0.03em",
          }}
        >
          <span className="text-[17px] font-[600] leading-none tracking-[-0.03em] text-[var(--fg)]">
            Web
          </span>
          <span className="text-[17px] font-[400] leading-none tracking-[-0.03em] text-[var(--ink-subtle)]">
            Observer
          </span>
        </span>
      ) : null}
    </span>
  );
}
