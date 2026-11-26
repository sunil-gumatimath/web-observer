import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

export function validateBuildEnv(phase: string): void {
  const publicInternalToken = (process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN ?? "").trim();
  const isProdBuild = phase === PHASE_PRODUCTION_BUILD || process.env.NODE_ENV === "production";
  if (isProdBuild && publicInternalToken && publicInternalToken !== "dev-internal-token") {
    throw new Error(
      "Refusing production build with a non-placeholder NEXT_PUBLIC_INTERNAL_API_TOKEN: " +
        "NEXT_PUBLIC_* values are inlined into the browser bundle.",
    );
  }
}

export default function createNextConfig(phase: string): NextConfig {
  validateBuildEnv(phase);
  return {
    // Silence multi-lockfile root inference when a parent package-lock exists
    turbopack: {
      root: process.cwd(),
    },
    // Allow loading dev resources (fonts, static chunks) when the app is opened
    // via 127.0.0.1 instead of localhost — otherwise Next blocks them and the
    // page appears to hang while loading.
    allowedDevOrigins: ["127.0.0.1", "localhost"],
  };
}
