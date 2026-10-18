"use client";

type LogoIconProps = {
  size?: number;
  className?: string;
};

/**
 * Minimal / Clean — Linear Theme
 * A focused target: centered dot + two precise rings + one active arc + ping.
 * Uses Linear lavender-blue (#5e6ad2) for the active ping.
 * ViewBox 0 0 32 32.
 */
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
        {/* soft inner highlight */}
        <rect x="0.5" y="0.5" width="31" height="31" rx="7.5" fill="#0f1011" />
        <rect x="0.5" y="0.5" width="31" height="31" rx="7.5" stroke="white" strokeOpacity="0.06" />

        {/* outer track — hairline */}
        <circle cx="16" cy="16" r="9.5" stroke="white" strokeOpacity="0.12" strokeWidth="0.95" />

        {/* active scanning arc — Linear lavender accent */}
        <path
          d="M 16 6.5 A 9.5 9.5 0 0 1 24.25 9.75"
          stroke="#5e6ad2"
          strokeWidth="1.55"
          strokeLinecap="round"
        />
        {/* small ping at arc tip */}
        <circle cx="24.25" cy="9.75" r="1.35" fill="#828fff" stroke="#0f1011" strokeWidth="0.9" />
        <circle cx="24.25" cy="9.75" r="2.45" fill="#5e6ad2" fillOpacity="0.25" />

        {/* middle ring */}
        <circle cx="16" cy="16" r="5.9" stroke="white" strokeWidth="1.35" strokeOpacity="0.9" />

        {/* center — the page being watched */}
        <circle cx="16" cy="16" r="2.35" fill="white" />
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
