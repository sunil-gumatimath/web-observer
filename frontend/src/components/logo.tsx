"use client";

type LogoIconProps = {
  size?: number;
  className?: string;
};

export function LogoIcon({ size = 32, className = "" }: LogoIconProps) {
  return (
    <span
      aria-hidden
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[8px] bg-[var(--surface-1)] border border-[var(--hairline-strong)] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] ${className}`}
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
        className="h-full w-full p-0.5"
      >
        {/* Terminal Prompt Chevron ❯ */}
        <path
          d="M9.5 10 L16 16 L9.5 22"
          stroke="#828fff"
          strokeWidth="2.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Glowing Cursor _ */}
        <path
          d="M18.5 21.5 H23.5"
          stroke="#34d399"
          strokeWidth="2.75"
          strokeLinecap="round"
        />
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

export function Logo({
  compact = false,
  iconSize = 32,
  className = "",
  responsiveWordmark = false,
}: LogoProps) {
  return (
    <span
      className={`inline-flex items-center gap-2.5 ${className}`}
      aria-label="Web Observer"
    >
      <LogoIcon size={iconSize} />
      {!compact ? (
        <span
          className={`inline-flex items-baseline gap-1.5 select-none ${
            responsiveWordmark ? "hidden sm:inline-flex" : ""
          }`}
          style={{
            fontFamily:
              'var(--font-display), "Linear Display", "SF Pro Display", Inter, -apple-system, sans-serif',
            letterSpacing: "-0.02em",
          }}
        >
          <span className="text-[16px] font-[600] leading-none text-[var(--fg)]">
            web
          </span>
          <span
            className="text-[13px] font-mono leading-none text-[var(--ink-tertiary)]"
            aria-hidden
          >
            /
          </span>
          <span className="text-[16px] font-[400] leading-none text-[var(--ink-subtle)]">
            observer
          </span>
        </span>
      ) : null}
    </span>
  );
}
