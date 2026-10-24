// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { contentSecurityPolicy, isProtectedPath } from "@/lib/security";

import { config, proxy } from "./proxy";

function request(path: string, cookie?: string) {
  return new NextRequest(new URL(path, "http://localhost:3000"), {
    headers: cookie ? { cookie } : {},
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("proxy", () => {
  it.each(["/select-company", "/c/6d6fc62d-05a1-41cf-b6e9-de1990e18288", "/account"])(
    "sends %s to the login page without a session cookie",
    (path) => {
      const response = proxy(request(`${path}?x=1`));

      expect(response.status).toBe(307);
      const location = new URL(response.headers.get("location")!);
      expect(location.pathname).toBe("/login");
      expect(location.searchParams.get("next")).toBe(`${path}?x=1`);
    },
  );

  it("lets requests with a session cookie through (the API still checks it)", () => {
    const response = proxy(request("/c/abc", "sessionid=whatever"));

    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it.each(["/login", "/forgot-password", "/reset-password", "/"])(
    "does not redirect public page %s",
    (path) => {
      expect(proxy(request(path)).headers.get("location")).toBeNull();
    },
  );

  it("sets a fresh CSP nonce on every response", () => {
    const first = proxy(request("/login")).headers.get("content-security-policy")!;
    const second = proxy(request("/login")).headers.get("content-security-policy")!;

    expect(first).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]{24}' 'strict-dynamic'/);
    expect(first).not.toBe(second);
    expect(proxy(request("/account")).headers.get("content-security-policy")).toContain(
      "frame-ancestors 'none'",
    );
  });

  it("does not intercept API calls or static files", () => {
    const [matcher] = config.matcher;
    const pattern = new RegExp(`^${matcher!.source}$`);
    expect(pattern.test("/api/v1/auth/me/")).toBe(false);
    expect(pattern.test("/_next/static/chunk.js")).toBe(false);
    expect(pattern.test("/login")).toBe(true);
    expect(pattern.test("/c/abc")).toBe(true);
  });
});

describe("content security policy", () => {
  it("is strict in production", () => {
    const csp = contentSecurityPolicy("n0nce", false);
    expect(csp).toContain("script-src 'self' 'nonce-n0nce' 'strict-dynamic'");
    expect(csp).toContain("style-src 'self' 'nonce-n0nce'");
    expect(csp).toContain("connect-src 'self'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("upgrade-insecure-requests");
    expect(csp).not.toContain("unsafe");
  });

  it("relaxes only what the development server needs", () => {
    const csp = contentSecurityPolicy("n0nce", true);
    expect(csp).toContain("'unsafe-eval'");
    expect(csp).toContain("style-src 'self' 'unsafe-inline'");
    expect(csp).not.toContain("upgrade-insecure-requests");
  });
});

describe("protected paths", () => {
  it("matches whole path segments only", () => {
    expect(isProtectedPath("/c")).toBe(true);
    expect(isProtectedPath("/accounting-info")).toBe(false);
    expect(isProtectedPath("/company")).toBe(false);
  });
});
