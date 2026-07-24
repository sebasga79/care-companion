import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Self-contained server bundle for a small Docker image (clean-install
  // ≤15 min gate, REL-001). Copies only the traced deps into the runner.
  output: "standalone",
  // Pin the workspace root to this package. Without it Turbopack walks up
  // and can pick a stray lockfile outside this repo (e.g. a sibling
  // ~/package-lock.json) as the root, which is wrong for this standalone
  // Next.js app inside source-meridian-agent/web.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
