import type { NextConfig } from "next";

// The browser talks only to this origin; /api/* is forwarded to the FastAPI server.
// Same origin means no CORS, first-party session cookies and a single address to open.
const apiOrigin = (process.env.SMARTARCHIVE_API_ORIGIN || "http://127.0.0.1:8000").replace(/\/$/, "");

const config: NextConfig = {
  distDir: process.env.SMARTARCHIVE_NEXT_DIR || ".next",
  poweredByHeader: false,
  devIndicators: false,
  experimental: { proxyClientMaxBodySize: "40mb", proxyTimeout: 120_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/(.*)", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Frame-Options", value: "DENY" },
    ] }];
  },
};
export default config;
