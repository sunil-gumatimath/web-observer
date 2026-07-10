import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--bg)",
        foreground: "var(--text)",
        brand: {
          50: "#f0f9ff",
          100: "#e0f2fe",
          200: "#bae6fd",
          300: "#7dd3fc",
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1",
        },
      },
      boxShadow: {
        glow: "0 0 40px -8px rgba(14, 165, 233, 0.45)",
        "glow-sm": "0 0 20px -6px rgba(14, 165, 233, 0.35)",
        card: "0 10px 40px -12px rgba(0, 0, 0, 0.55)",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "brand-gradient": "linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%)",
      },
      animation: {
        "fade-in-up": "fade-in-up 0.45s ease-out both",
      },
    },
  },
  plugins: [],
} satisfies Config;
