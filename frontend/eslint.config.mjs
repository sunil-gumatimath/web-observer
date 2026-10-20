import clerkNext from "@clerk/eslint-plugin/next";
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
  {
    // Clerk's resource-based auth model. Authorization is no longer decided by
    // route matching in proxy.ts, so every server entrypoint (page, layout,
    // route handler, Server Function) under the authenticated route group must
    // perform its own check. Client components are skipped by the rule — they
    // reach data through the backend API, which validates the Clerk JWT.
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "@clerk/next": clerkNext },
    rules: {
      "@clerk/next/require-auth-protection": [
        "error",
        {
          protected: ["src/app/(app)/**"],
          public: [
            "src/app/(docs)/**",
            "src/app/sign-in/**",
            "src/app/sign-up/**",
            "src/app/invite/**",
            "src/app/share/**",
          ],
        },
      ],
    },
  },
];

export default eslintConfig;
