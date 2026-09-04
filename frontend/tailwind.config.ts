import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--bg)",
        foreground: "var(--fg)",
        elevated: "var(--bg-elevated)",
        card: "var(--bg-card)",
        muted: "var(--muted)",
        "border-default": "var(--border)",
        "border-strong": "var(--border-strong)",
        "border-soft": "var(--border-soft)",
        accent: "var(--accent)",
        "accent-strong": "var(--accent-hover)",
        ring: "var(--accent)",
        surface: "var(--surface)",
        brand: {
          50: "#eef4fe",
          100: "#d8e6fd",
          200: "#b0ccfb",
          300: "#7fa9f7",
          400: "#4c82ef",
          500: "#1863dc",
          600: "#1559c4",
          700: "#124eaa",
        },
      },
      boxShadow: {
        glow: "0 4px 16px rgba(0, 0, 0, 0.06)",
        "glow-sm": "0 4px 16px rgba(0, 0, 0, 0.06)",
        card: "none",
      },
      fontFamily: {
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        body: ["var(--font-body)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        cohere: "22px",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "brand-gradient": "linear-gradient(135deg, #1863dc 0%, #4c6ee6 100%)",
      },
      animation: {
        "fade-in-up": "fade-in-up 0.45s ease-out both",
      },
    },
  },
  plugins: [],
} satisfies Config;
