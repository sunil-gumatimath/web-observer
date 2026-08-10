import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * ESLint 9 flat config using Next.js 16's native flat-config entry points.
 * (The previous FlatCompat-based config crashed ESLint with a circular-JSON
 * validation error on this dependency set.)
 */
/** @type {import("eslint").Linter.Config[]} */
const eslintConfig = [
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Codebase convention: loading/reset state and the next-themes
      // `mounted` hydration gate are set synchronously at effect start.
      // This rule is advisory here — keep it as a warning so it stays
      // visible without failing the build.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default eslintConfig;
