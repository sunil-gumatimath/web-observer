import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Silence multi-lockfile root inference when a parent package-lock exists
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
