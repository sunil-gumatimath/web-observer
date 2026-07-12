/**
 * Shared Clerk appearance object for SignIn / SignUp pages.
 * Adapts colors to the active theme so Clerk components match the app shell.
 */
export function clerkAppearance(isDark: boolean) {
  return {
    variables: {
      colorPrimary: "#0ea5e9",
      colorBackground: isDark ? "#0b1220" : "#ffffff",
      colorInputBackground: isDark ? "#020617" : "#f8fafc",
      colorInputText: isDark ? "#e2e8f0" : "#0f172a",
      colorText: isDark ? "#e2e8f0" : "#0f172a",
      colorTextSecondary: isDark ? "#94a3b8" : "#64748b",
      colorNeutral: isDark ? "#1e293b" : "#e2e8f0",
      borderRadius: "0.75rem",
    },
    elements: {
      rootBox: "mx-auto w-full max-w-md",
      card: isDark
        ? "border border-white/10 bg-slate-900/80 shadow-2xl shadow-black/40 backdrop-blur-xl"
        : "border border-slate-200 bg-white shadow-xl shadow-slate-300/30 backdrop-blur-xl",
      headerTitle: isDark ? "text-white" : "text-slate-900",
      headerSubtitle: isDark ? "text-slate-400" : "text-slate-500",
      socialButtonsBlockButton: isDark
        ? "border border-white/10 bg-slate-950/60 text-slate-100 hover:bg-slate-800"
        : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-100",
      formButtonPrimary: "bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-500/20",
      footerActionLink: "text-sky-600 hover:text-sky-700 dark:text-sky-400 dark:hover:text-sky-300",
      formFieldInput: isDark
        ? "border-white/10 bg-slate-950 text-slate-100"
        : "border-slate-300 bg-white text-slate-900",
    },
  };
}
