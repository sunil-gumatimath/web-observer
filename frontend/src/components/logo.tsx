"use client";

type LogoIconProps = {
  size?: number;
  className?: string;
};

/**
 * Minimal / Clean — V2
 * No literal eye, no busy pulse zig-zag.
 * A focused target: centered dot + two precise rings + one active arc + ping.
 * Reads at 16px, calm on light header and dark header.
 * ViewBox 0 0 32 32.
 */
export function LogoIcon({ size = 36, className = "" }: LogoIconProps) {
  return (
    <span
      aria-hidden
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[10px] bg-slate-900 shadow-[0_1px_2px_rgba(0,0,0,0.08),0_4px_12px_rgba(0,0,0,0.10)] ring-1 ring-black/5 dark:bg-slate-900 dark:ring-white/10 ${className}`}
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
        {/* soft inner highlight */}
        <rect x="0.5" y="0.5" width="31" height="31" rx="9.5" fill="#0f172a" />
        <rect x="0.5" y="0.5" width="31" height="31" rx="9.5" stroke="white" strokeOpacity="0.08" />

        {/* outer track — hairline */}
        <circle cx="16" cy="16" r="9.5" stroke="white" strokeOpacity="0.14" strokeWidth="0.95" />

        {/* active scanning arc — the only accent */}
        <path
          d="M 16 6.5 A 9.5 9.5 0 0 1 24.25 9.75"
          stroke="#38bdf8"
          strokeWidth="1.55"
          strokeLinecap="round"
        />
        {/* small ping at arc tip */}
        <circle cx="24.25" cy="9.75" r="1.35" fill="#38bdf8" stroke="#0f172a" strokeWidth="0.9" />
        <circle cx="24.25" cy="9.75" r="2.45" fill="#38bdf8" fillOpacity="0.18" />

        {/* middle ring */}
        <circle cx="16" cy="16" r="5.9" stroke="white" strokeWidth="1.35" strokeOpacity="0.95" />

        {/* center — the page being watched */}
        <circle cx="16" cy="16" r="2.35" fill="white" />
        <circle cx="16" cy="16" r="2.35" stroke="#38bdf8" strokeOpacity="0.0" />
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

export function Logo({ compact = false, iconSize = 36, className = "", responsiveWordmark = false }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`} aria-label="Web Observer">
      <LogoIcon size={iconSize} />
      {!compact ? (
        <span
          className={`inline-flex items-baseline gap-[0.28em] select-none ${responsiveWordmark ? "hidden sm:inline-flex" : ""}`}
          style={{
            fontFamily:
              'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
            letterSpacing: "-0.03em",
          }}
        >
          <span className="text-[18.5px] font-[700] leading-none tracking-[-0.03em] text-slate-900 dark:text-white">
            Web
          </span>
          <span className="text-[18.5px] font-[500] leading-none tracking-[-0.03em] text-slate-500 dark:text-slate-300">
            Observer
          </span>
        </span>
      ) : null}
    </span>
  );
}
