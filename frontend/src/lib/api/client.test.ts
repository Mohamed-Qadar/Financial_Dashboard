import { describe, expect, it, vi } from "vitest";

import { apiRequest, type ClientDeps, readCookie } from "./client";
import { companies } from "./endpoints";
import { ApiError } from "./errors";

const COMPANY = "6d6fc62d-05a1-41cf-b6e9-de1990e18288";

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

/** A fake browser: a cookie jar and a fetch that records calls. */
function fakeBrowser(cookies: string, ...responses: Response[]) {
  const jar = { cookies };
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    if (String(input) === "/api/v1/auth/csrf/") {
      jar.cookies = "csrftoken=fresh-token";
      return new Response(null, { status: 204 });
    }
    const next = responses.shift();
    if (!next) throw new Error("unexpected request");
    return next;
  });
  const deps: ClientDeps = { fetch: fetchMock, readCookies: () => jar.cookies };
  const headersOf = (call: number) => new Headers(fetchMock.mock.calls[call]![1]!.headers);
  return { deps, fetchMock, headersOf };
}

describe("apiRequest", () => {
  it("sends same-origin GETs without a CSRF token or company header", async () => {
    const { deps, fetchMock, headersOf } = fakeBrowser("csrftoken=t1", json(200, { ok: 1 }));

    await expect(apiRequest("/api/v1/auth/me/", {}, deps)).resolves.toEqual({ ok: 1 });

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/auth/me/");
    expect(init?.credentials).toBe("same-origin");
    expect(init?.cache).toBe("no-store");
    expect(headersOf(0).has("X-CSRFToken")).toBe(false);
    expect(headersOf(0).has("X-Company-ID")).toBe(false);
  });

  it("sends the CSRF cookie value with unsafe requests", async () => {
    const { deps, headersOf, fetchMock } = fakeBrowser(
      "other=1; csrftoken=abc%3D123",
      new Response(null, { status: 204 }),
    );

    await apiRequest("/api/v1/auth/logout/", { method: "POST" }, deps);

    expect(headersOf(0).get("X-CSRFToken")).toBe("abc=123");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("fetches a CSRF cookie first when there is none", async () => {
    const { deps, fetchMock, headersOf } = fakeBrowser("", json(200, { id: "u" }));

    await apiRequest("/api/v1/auth/login/", { method: "POST", body: { email: "a" } }, deps);

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/auth/csrf/",
      "/api/v1/auth/login/",
    ]);
    expect(headersOf(1).get("X-CSRFToken")).toBe("fresh-token");
    expect(headersOf(1).get("Content-Type")).toBe("application/json");
    expect(fetchMock.mock.calls[1]![1]!.body).toBe('{"email":"a"}');
  });

  it("adds the company header only for company-scoped calls", async () => {
    const { deps, headersOf } = fakeBrowser("", json(200, { id: COMPANY }));

    await companies.active(COMPANY, undefined, deps);

    expect(headersOf(0).get("X-Company-ID")).toBe(COMPANY);
  });

  it.each(["not-a-uuid", `${COMPANY},${COMPANY}`, ` ${COMPANY}`, ""])(
    "refuses to send company id %j",
    async (companyId) => {
      const { deps, fetchMock } = fakeBrowser("");

      await expect(apiRequest("/api/v1/company/", { companyId }, deps)).rejects.toMatchObject({
        code: "company_required",
      });
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it.each(["https://evil.example/api/v1/", "/api/v2/x/", "/api/v1//evil", "/api/v1/../admin/"])(
    "refuses paths outside the API: %s",
    async (path) => {
      const { deps } = fakeBrowser("");
      await expect(apiRequest(path, {}, deps)).rejects.toThrow("Refusing");
    },
  );

  it("turns the error envelope into an ApiError", async () => {
    const { deps } = fakeBrowser(
      "",
      json(
        429,
        { error: { code: "throttled", message: "Slow down.", request_id: "r-1" } },
        { "Retry-After": "90" },
      ),
    );

    const error = await apiRequest("/api/v1/auth/me/", {}, deps).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 429,
      code: "throttled",
      requestId: "r-1",
      retryAfterSeconds: 90,
    });
  });

  it("reports non-JSON errors and network failures with client codes", async () => {
    const html = fakeBrowser("", new Response("<html>Bad gateway</html>", { status: 502 }));
    await expect(apiRequest("/api/v1/auth/me/", {}, html.deps)).rejects.toMatchObject({
      status: 502,
      code: "server_error",
    });

    const offline: ClientDeps = {
      fetch: vi.fn<typeof fetch>().mockRejectedValue(new TypeError("Failed to fetch")),
      readCookies: () => "",
    };
    await expect(apiRequest("/api/v1/auth/me/", {}, offline)).rejects.toMatchObject({
      status: 0,
      code: "network_error",
    });
  });

  it("returns nothing for 202 and 204", async () => {
    const { deps } = fakeBrowser("csrftoken=t", new Response(null, { status: 202 }));
    await expect(
      apiRequest("/api/v1/auth/password/reset/", { method: "POST", body: {} }, deps),
    ).resolves.toBeUndefined();
  });
});

describe("validation errors", () => {
  it("exposes field messages", () => {
    const error = new ApiError(400, "validation_error", "Invalid input.", undefined, {
      new_password: ["Too short.", 3],
      other: "ignored",
    });
    expect(error.fieldErrors()).toEqual({ new_password: ["Too short."] });
  });
});

describe("readCookie", () => {
  it("finds a cookie among others", () => {
    expect(readCookie("a=1; csrftoken=xyz; b=2", "csrftoken")).toBe("xyz");
    expect(readCookie("xcsrftoken=no", "csrftoken")).toBeUndefined();
    expect(readCookie("", "csrftoken")).toBeUndefined();
  });
});
