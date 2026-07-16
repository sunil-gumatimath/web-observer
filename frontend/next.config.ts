import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Silence multi-lockfile root inference when a parent package-lock exists
  turbopack: {
    root: process.cwd(),
  },
  // Allow loading dev resources (fonts, static chunks) when the app is opened
  // via 127.0.0.1 instead of localhost — otherwise Next blocks them and the
  // page appears to hang while loading.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
