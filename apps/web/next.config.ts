import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A self-contained server in .next/standalone, so the Docker image needs no node_modules.
  // Not on Vercel, which builds and serves Next.js itself (VERCEL is set in its builds).
  output: process.env.VERCEL ? undefined : "standalone",
};

export default nextConfig;
