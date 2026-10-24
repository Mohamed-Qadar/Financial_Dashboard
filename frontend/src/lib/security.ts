/**
 * Request interception rules used by src/proxy.ts (pure functions, unit-tested).
 *
 * The redirect to the login page only improves navigation: it checks that a session cookie
 * exists, not that it is valid. Authorization stays on the server, which answers 403 for an
 * ended session and 404 for a company without access.
 */

/** Django's default SESSION_COOKIE_NAME (backend/config/settings.py does not change it). */
export const SESSION_COOKIE = "sessionid";

const PROTECTED_PREFIXES = ["/select-company", "/c", "/account"];

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function createNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

/**
 * Content Security Policy with a per-request nonce (Next.js 16 applies it to its own scripts
 * and styles during dynamic rendering). Development additionally needs `eval` (React's dev
 * tooling), inline styles (webpack's style injection; a nonce would make browsers ignore
 * 'unsafe-inline') and the hot-reload websocket.
 */
export function contentSecurityPolicy(nonce: string, isDevelopment: boolean): string {
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDevelopment ? " 'unsafe-eval'" : ""}`,
    isDevelopment ? "style-src 'self' 'unsafe-inline'" : `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self' data: blob:",
    "font-src 'self'",
    isDevelopment ? "connect-src 'self' ws:" : "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (!isDevelopment) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}
