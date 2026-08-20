export function LogoIcon({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <span
      className={className}
      style={{ width: size, height: size, display: "inline-flex" }}
      aria-hidden="true"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 32 32"
        width={size}
        height={size}
        role="img"
        className="h-full w-full"
      >
        <defs>
          <linearGradient id="wo-g" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="9" fill="url(#wo-g)" />
        {/* eye shape */}
        <path
          d="M6.2 16C6.2 16 9.9 8.4 16 8.4C22.1 8.4 25.8 16 25.8 16C25.8 16 22.1 23.6 16 23.6C9.9 23.6 6.2 16 6.2 16Z"
          fill="white"
          fillOpacity={0.97}
        />
        {/* iris */}
        <circle cx="16" cy="16" r={5.4} fill="#0ea5e9" stroke="white" strokeWidth={1.05} />
        <circle cx="16" cy="16" r={3.9} fill="none" stroke="white" strokeOpacity={0.35} strokeWidth={0.6} />
        {/* pupil */}
        <circle cx="16" cy="16" r={2.35} fill="#0f172a" />
        {/* highlight */}
        <circle cx="17.6" cy="14.25" r={1} fill="white" />
        {/* pulse / notification dot - indicates "change detected" */}
        <g>
          <circle cx="25.5" cy="6.8" r={2.1} fill="#22d3ee" stroke="white" strokeWidth={1.15} />
          <circle cx="25.5" cy="6.8" r={0.7} fill="white" opacity={0.95} />
        </g>
      </svg>
    </span>
  );
}

export function Logo({ compact = false, iconSize = 36 }: { compact?: boolean; iconSize?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5 font-semibold tracking-tight text-[var(--text)]">
      <LogoIcon size={iconSize} className="shrink-0 rounded-xl shadow-glow-sm" />
      {!compact ? (
        <span className="hidden sm:inline text-[17px] font-bold tracking-[-0.02em]">Web Observer</span>
      ) : null}
    </span>
  );
}
