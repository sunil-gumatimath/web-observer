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
        fill="none"
        role="img"
        className="h-full w-full"
      >
        <defs>
          {/* Screen Bezel Metallic Slate Gradient */}
          <linearGradient id="comp-bezel" x1="0" y1="2" x2="0" y2="22" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#1e293b" />
            <stop offset="100%" stopColor="#0f172a" />
          </linearGradient>

          {/* Outer Bezel Dual-Tone Border (High contrast on both white and dark themes) */}
          <linearGradient id="comp-border" x1="2" y1="2" x2="30" y2="22" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.85" />
            <stop offset="40%" stopColor="#94a3b8" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0.85" />
          </linearGradient>

          {/* Deep Obsidian Display Screen Viewport */}
          <linearGradient id="comp-screen" x1="4" y1="4" x2="28" y2="19" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#030712" />
            <stop offset="50%" stopColor="#0b1329" />
            <stop offset="100%" stopColor="#080e1e" />
          </linearGradient>

          {/* Pulse Waveform Gradient */}
          <linearGradient id="comp-pulse-grad" x1="5" y1="12" x2="27" y2="12" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#0284c7" />
            <stop offset="40%" stopColor="#38bdf8" />
            <stop offset="70%" stopColor="#818cf8" />
            <stop offset="100%" stopColor="#c084fc" />
          </linearGradient>

          {/* Wave Glow Area Gradient */}
          <linearGradient id="comp-wave-area" x1="16" y1="8" x2="16" y2="15" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
          </linearGradient>

          {/* Stand Gradient */}
          <linearGradient id="comp-stand" x1="0" y1="21" x2="0" y2="28" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#64748b" />
            <stop offset="100%" stopColor="#334155" />
          </linearGradient>
        </defs>

        {/* Drop Shadow backing for depth on pure white backgrounds */}
        <rect x="2.5" y="2.5" width="27" height="19" rx="3.5" fill="#000000" fillOpacity="0.12" />

        {/* Monitor Outer Bezel */}
        <rect x="2.5" y="2.5" width="27" height="18.5" rx="3.5" fill="url(#comp-bezel)" stroke="url(#comp-border)" strokeWidth="0.9" />

        {/* Display Screen Glass */}
        <rect x="4.2" y="4.2" width="23.6" height="14" rx="2" fill="url(#comp-screen)" stroke="#1e293b" strokeWidth="0.5" />

        {/* Window Controls (Red, Yellow, Green) */}
        <circle cx="6.8" cy="6.4" r="0.75" fill="#f43f5e" />
        <circle cx="8.8" cy="6.4" r="0.75" fill="#fbbf24" />
        <circle cx="10.8" cy="6.4" r="0.75" fill="#34d399" />

        {/* Radar Telemetry Grid on Screen */}
        <circle cx="16" cy="11.5" r="4.5" stroke="#38bdf8" strokeOpacity="0.18" strokeWidth="0.5" strokeDasharray="2 1.5" />
        <line x1="5.5" y1="11.5" x2="26.5" y2="11.5" stroke="#38bdf8" strokeOpacity="0.12" strokeWidth="0.5" />

        {/* Wave Glow Area */}
        <path
          d="M 5.5 11.5 L 11 11.5 L 13.5 8 L 15.5 15 L 18 9 L 20 11.5 L 26.5 11.5 L 26.5 16 L 5.5 16 Z"
          fill="url(#comp-wave-area)"
        />

        {/* Dynamic Live Change Pulse / Waveform */}
        <path
          d="M 5.5 11.5 L 11 11.5 L 13.5 8 L 15.5 15 L 18 9 L 20 11.5 L 26.5 11.5"
          stroke="url(#comp-pulse-grad)"
          strokeWidth="1.3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Active Signal Beacon on Waveform Peak */}
        <circle cx="18" cy="9" r="2.2" fill="#22d3ee" fillOpacity="0.25" />
        <circle cx="18" cy="9" r="1.1" fill="#22d3ee" stroke="#ffffff" strokeWidth="0.5" />
        <circle cx="18" cy="9" r="0.45" fill="#ffffff" />

        {/* Live Pulse Beacon / Alert Node */}
        <circle cx="24" cy="6.4" r="1.2" fill="#38bdf8" fillOpacity="0.3" />
        <circle cx="24" cy="6.4" r="0.7" fill="#38bdf8" />
        <circle cx="24" cy="6.4" r="0.3" fill="#ffffff" />

        {/* Monitor Stand Neck */}
        <path d="M 14.5 21 L 17.5 21 L 18.2 25.5 L 13.8 25.5 Z" fill="url(#comp-stand)" stroke="#475569" strokeWidth="0.5" />

        {/* Monitor Stand Base */}
        <rect x="9.5" y="25.5" width="13" height="2.2" rx="1.1" fill="url(#comp-stand)" stroke="#64748b" strokeWidth="0.6" />
        <line x1="11.5" y1="26" x2="20.5" y2="26" stroke="#94a3b8" strokeWidth="0.5" strokeLinecap="round" />
      </svg>
    </span>
  );
}

export function Logo({ compact = false, iconSize = 36 }: { compact?: boolean; iconSize?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5 font-semibold tracking-tight text-slate-900 dark:text-white">
      <LogoIcon size={iconSize} className="shrink-0" />
      {!compact ? (
        <span className="hidden sm:inline text-[17px] font-bold tracking-[-0.02em]">
          Web <span className="text-sky-500 dark:text-sky-400">Observer</span>
        </span>
      ) : null}
    </span>
  );
}
