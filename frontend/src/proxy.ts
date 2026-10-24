import { type NextRequest, NextResponse } from "next/server";

import { loginPath } from "@/lib/redirects";
import {
  contentSecurityPolicy,
  createNonce,
  isProtectedPath,
  SESSION_COOKIE,
} from "@/lib/security";

/**
 * Next.js 16 proxy (formerly middleware): a per-request CSP nonce on every page, and a
 * redirect to the login page for app pages requested without a session cookie.
 * API calls (/api/*) are not intercepted; Django handles them.
 */
export function proxy(request: NextRequest) {
  const nonce = createNonce();
  const csp = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");
  const { pathname, search } = request.nextUrl;

  if (isProtectedPath(pathname) && !request.cookies.has(SESSION_COOKIE)) {
    const response = NextResponse.redirect(new URL(loginPath(`${pathname}${search}`), request.url));
    response.headers.set("Content-Security-Policy", csp);
    return response;
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api/|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
