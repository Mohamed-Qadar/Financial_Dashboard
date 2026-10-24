/**
 * Safe post-login redirects: only paths of this site, never another origin
 * (open-redirect protection). Anything doubtful falls back to the default.
 */
// `auto=1`: with exactly one company, the picker opens it directly.
export const DEFAULT_AFTER_LOGIN = "/select-company?auto=1";
const PLACEHOLDER_ORIGIN = "https://erp.invalid";
const MAX_LENGTH = 512;
const AUTH_PAGES = ["/login", "/forgot-password", "/reset-password"];

export function safeNextPath(raw: string | null | undefined, fallback = DEFAULT_AFTER_LOGIN): string {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > MAX_LENGTH) return fallback;
  // Must be a single-slash absolute path: rejects "//evil", "/\evil", "https:", "javascript:".
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return fallback;
  // Control characters (incl. tab/newline, which browsers strip inside URLs).
  if (/[\u0000-\u001f\u007f]/.test(raw)) return fallback;
  let url: URL;
  try {
    url = new URL(raw, PLACEHOLDER_ORIGIN);
  } catch {
    return fallback;
  }
  if (url.origin !== PLACEHOLDER_ORIGIN) return fallback;
  // Encoded tricks ("/%0a//evil", "/%2F%2Fevil"): judge the decoded path as well.
  let decoded: string;
  try {
    decoded = decodeURIComponent(url.pathname);
  } catch {
    return fallback;
  }
  if (/[\u0000-\u001f\u007f\\]/.test(decoded) || decoded.includes("//")) return fallback;
  if (AUTH_PAGES.some((page) => url.pathname === page || url.pathname.startsWith(`${page}/`))) {
    return fallback;
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

/** The login page that returns to `currentPath` afterwards. */
export function loginPath(currentPath?: string, reason?: "expired"): string {
  const params = new URLSearchParams();
  if (currentPath) {
    const next = safeNextPath(currentPath, "");
    if (next) params.set("next", next);
  }
  if (reason) params.set("reason", reason);
  const query = params.toString();
  return query ? `/login?${query}` : "/login";
}
