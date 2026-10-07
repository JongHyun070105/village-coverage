import type { NextConfig } from "next";
import { readFileSync } from "node:fs";
import path from "node:path";

function loadRootPublicEnvironment() {
  const envPath = path.resolve(process.cwd(), "..", ".env");
  let contents: string;
  try {
    contents = readFileSync(envPath, "utf8");
  } catch {
    return;
  }

  for (const line of contents.split(/\r?\n/)) {
    const match = line.match(/^\s*(NEXT_PUBLIC_[A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (!match || process.env[match[1]]) continue;
    let value = match[2];
    if (value.length >= 2 && ["'", '"'].includes(value[0]) && value.at(-1) === value[0]) {
      value = value.slice(1, -1);
    }
    process.env[match[1]] = value;
  }
}

loadRootPublicEnvironment();

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
        ],
      },
    ];
  },
};

export default nextConfig;
