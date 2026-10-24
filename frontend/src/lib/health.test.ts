import { describe, expect, it, vi } from "vitest";

import { getSystemStatus } from "./health";

function fetchReturning(status: number) {
  return vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status }));
}

describe("getSystemStatus", () => {
  it("calls the readiness endpoint of the given backend", async () => {
    const fetchMock = fetchReturning(200);

    await getSystemStatus("http://backend:8000", fetchMock);

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("http://backend:8000/api/v1/health/ready/");
    expect(init?.cache).toBe("no-store");
  });

  it("reports everything ok on 200", async () => {
    await expect(getSystemStatus("http://backend", fetchReturning(200))).resolves.toEqual({
      api: "ok",
      database: "ok",
    });
  });

  it("reports the database unavailable on 503", async () => {
    await expect(getSystemStatus("http://backend", fetchReturning(503))).resolves.toEqual({
      api: "ok",
      database: "unavailable",
    });
  });

  it("reports an API error on other statuses", async () => {
    await expect(getSystemStatus("http://backend", fetchReturning(500))).resolves.toEqual({
      api: "error",
      database: "unknown",
    });
  });

  it("reports the API unreachable when the request fails", async () => {
    const failing = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("fetch failed"));

    await expect(getSystemStatus("http://backend", failing)).resolves.toEqual({
      api: "unreachable",
      database: "unknown",
    });
  });
});
