/**
 * Browser API client for the Django backend (docs/SECURITY.md § 2–3).
 *
 * - Same origin only: paths must start with /api/v1/; Next.js rewrites them to Django, so the
 *   session cookie stays first-party and is sent automatically (`credentials: same-origin`).
 * - CSRF: every unsafe request carries the `csrftoken` cookie value in `X-CSRFToken`; if
 *   the cookie is missing it is fetched first from `GET /api/v1/auth/csrf/`. The token is
 *   read fresh for every request because Django rotates it at login.
 * - Active company: `X-Company-ID` is added only when a company id is given and is a UUID.
 *   It is a selector; the server checks membership on every request.
 * - Errors become `ApiError` with the backend's error code. Nothing here logs tokens,
 *   cookies or request bodies.
 */
import { isUuid } from "@/lib/uuid";

import { ApiError, errorFromResponse } from "./errors";

export const API_PREFIX = "/api/v1/";
export const CSRF_COOKIE = "csrftoken";
const CSRF_PATH = "/api/v1/auth/csrf/";
const SAFE_METHODS = new Set(["GET", "HEAD"]);

export interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  companyId?: string;
  signal?: AbortSignal;
}

export interface ClientDeps {
  fetch: typeof fetch;
  readCookies: () => string;
}

function browserDeps(): ClientDeps {
  return {
    fetch: (input, init) => globalThis.fetch(input, init),
    readCookies: () => document.cookie,
  };
}

export function readCookie(cookies: string, name: string): string | undefined {
  for (const part of cookies.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) {
      const value = rest.join("=");
      return value === "" ? undefined : decodeURIComponent(value);
    }
  }
  return undefined;
}

async function send(deps: ClientDeps, path: string, init: RequestInit): Promise<Response> {
  try {
    return await deps.fetch(path, { ...init, credentials: "same-origin", cache: "no-store" });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "The server could not be reached.");
  }
}

async function csrfToken(deps: ClientDeps): Promise<string> {
  const existing = readCookie(deps.readCookies(), CSRF_COOKIE);
  if (existing) return existing;
  const response = await send(deps, CSRF_PATH, { method: "GET" });
  if (!response.ok) throw await errorFromResponse(response);
  const token = readCookie(deps.readCookies(), CSRF_COOKIE);
  if (!token) throw new ApiError(0, "csrf_failed", "No CSRF cookie was set.");
  return token;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
  deps: ClientDeps = browserDeps(),
): Promise<T> {
  if (!path.startsWith(API_PREFIX) || path.includes("//") || path.includes("..")) {
    throw new Error(`Refusing to call a path outside ${API_PREFIX}: ${path}`);
  }
  const method = options.method ?? "GET";
  const headers = new Headers({ Accept: "application/json" });
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (!SAFE_METHODS.has(method)) headers.set("X-CSRFToken", await csrfToken(deps));
  if (options.companyId !== undefined) {
    if (!isUuid(options.companyId)) {
      throw new ApiError(400, "company_required", "Invalid company id.");
    }
    headers.set("X-Company-ID", options.companyId);
  }

  const response = await send(deps, path, {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204 || response.status === 202) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(response.status, "server_error", "The response was not valid JSON.");
  }
}
