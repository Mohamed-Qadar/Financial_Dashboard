import type { NextConfig } from "next";

// Server-side address of the Django API (container network name in Docker Compose).
const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Development-only badge; bottom-left would cover the sidebar's collapse control.
  devIndicators: { position: "bottom-right" },
  // Django API URLs end with "/"; do not let Next.js redirect them to the slash-less form.
  skipTrailingSlashRedirect: true,
  async headers() {
    // Pages only: Django sets its own headers on /api responses. The Content Security Policy
    // is set per request (with a nonce) in src/proxy.ts.
    return [
      {
        source: "/((?!api/).*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          // Password-reset links carry a token in the query string: never send it onwards.
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
  async rewrites() {
    // The browser only talks to this origin, so session cookies stay first-party.
    // ":path*" drops a trailing slash, so slash-terminated URLs need their own rule first;
    // otherwise Django's APPEND_SLASH redirect and this rewrite loop forever.
    return [
      { source: "/api/:path*/", destination: `${backendUrl}/api/:path*/` },
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
    ];
  },
};

export default nextConfig;
