/**
 * Shared Clerk appearance object for SignIn / SignUp pages.
 * Adapts colors to the active theme so Clerk components match the app shell.
 */
export function clerkAppearance(isDark: boolean) {
  return {
    variables: {
      colorPrimary: "#1863dc",
      colorBackground: isDark ? "#17171c" : "#ffffff",
      colorInputBackground: isDark ? "#101014" : "#ffffff",
      colorInputText: isDark ? "#ffffff" : "#000000",
      colorText: isDark ? "#ffffff" : "#000000",
      colorTextSecondary: isDark ? "#9a9aa5" : "#93939f",
      colorNeutral: isDark ? "#34343c" : "#d9d9dd",
      borderRadius: "8px",
    },
    elements: {
      rootBox: "mx-auto w-full max-w-md",
      card: isDark
        ? "border border-white/10 bg-[#1e1e24] shadow-none"
        : "border border-[#f2f2f2] bg-white shadow-none",
      headerTitle: isDark ? "text-white" : "text-black",
      headerSubtitle: isDark ? "text-neutral-400" : "text-[#93939f]",
      socialButtonsBlockButton: isDark
        ? "border border-white/10 bg-black text-white hover:bg-neutral-800"
        : "border border-[#d9d9dd] bg-white text-black hover:text-[#1863dc]",
      formButtonPrimary: "bg-black hover:bg-neutral-800 text-white dark:bg-white dark:hover:bg-neutral-200 dark:text-black",
      footerActionLink: isDark
        ? "text-[#6b9bff] hover:text-[#86adff]"
        : "text-[#1863dc] hover:text-[#1559c4]",
      formFieldInput: isDark
        ? "border-white/10 bg-black text-white"
        : "border-[#d9d9dd] bg-white text-black",
    },
  };
}
