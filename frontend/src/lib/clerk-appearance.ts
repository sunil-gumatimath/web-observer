/**
 * Shared Clerk appearance object for SignIn / SignUp pages.
 * Adapts colors to the Linear design system from DESIGN.md.
 */
export function clerkAppearance(isDark: boolean) {
  return {
    variables: {
      colorPrimary: "#5e6ad2",
      colorBackground: isDark ? "#0f1011" : "#ffffff",
      colorInputBackground: isDark ? "#010102" : "#f5f6f6",
      colorInputText: isDark ? "#f7f8f8" : "#08090a",
      colorText: isDark ? "#f7f8f8" : "#08090a",
      colorTextSecondary: isDark ? "#8a8f98" : "#62666d",
      colorNeutral: isDark ? "#23252a" : "#e2e4e8",
      borderRadius: "8px",
    },
    elements: {
      rootBox: "mx-auto w-full max-w-md",
      card: isDark
        ? "border border-[#23252a] bg-[#0f1011] shadow-none rounded-[12px]"
        : "border border-[#e2e4e8] bg-white shadow-none rounded-[12px]",
      headerTitle: isDark ? "text-[#f7f8f8] tracking-tight" : "text-[#08090a] tracking-tight",
      headerSubtitle: isDark ? "text-[#8a8f98]" : "text-[#62666d]",
      socialButtonsBlockButton: isDark
        ? "border border-[#23252a] bg-[#141516] text-[#f7f8f8] hover:bg-[#18191a] rounded-[8px]"
        : "border border-[#e2e4e8] bg-[#f5f6f6] text-[#08090a] hover:bg-[#ebecee] rounded-[8px]",
      formButtonPrimary: "bg-[#5e6ad2] hover:bg-[#828fff] text-white rounded-[8px] font-medium transition",
      footerActionLink: isDark
        ? "text-[#828fff] hover:text-[#5e6ad2]"
        : "text-[#5e6ad2] hover:text-[#4b55be]",
      formFieldInput: isDark
        ? "border-[#23252a] bg-[#010102] text-[#f7f8f8] rounded-[8px] focus:border-[#5e6ad2]"
        : "border-[#e2e4e8] bg-[#ffffff] text-[#08090a] rounded-[8px] focus:border-[#5e6ad2]",
    },
  };
}
