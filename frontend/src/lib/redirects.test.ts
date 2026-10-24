import { describe, expect, it } from "vitest";

import { DEFAULT_AFTER_LOGIN, loginPath, safeNextPath } from "./redirects";

describe("safeNextPath", () => {
  it.each([
    "/select-company",
    "/c/6d6fc62d-05a1-41cf-b6e9-de1990e18288",
    "/c/6d6fc62d-05a1-41cf-b6e9-de1990e18288/account?tab=1#x",
    "/account",
  ])("keeps the internal path %s", (path) => {
    expect(safeNextPath(path)).toBe(path);
  });

  it.each([
    null,
    undefined,
    "",
    "https://evil.example/",
    "//evil.example/path",
    "/\\evil.example",
    "\\\\evil.example",
    "javascript:alert(1)",
    "evil.example",
    "/%0a//evil.example",
    "/%2F%2Fevil.example",
    "/%5Cevil.example",
    "/%E0%A4%A",
    "/\t/evil.example",
    "/login",
    "/login?next=/login",
    "/reset-password?uid=a&token=b",
    `/${"a".repeat(600)}`,
  ])("rejects %j", (value) => {
    expect(safeNextPath(value)).toBe(DEFAULT_AFTER_LOGIN);
  });

  it("normalises dot segments without leaving the site", () => {
    expect(safeNextPath("/c/../account")).toBe("/account");
  });
});

describe("loginPath", () => {
  it("returns to the current page after login", () => {
    expect(loginPath("/c/abc?x=1", "expired")).toBe("/login?next=%2Fc%2Fabc%3Fx%3D1&reason=expired");
  });

  it("drops unsafe return paths", () => {
    expect(loginPath("//evil.example")).toBe("/login");
    expect(loginPath()).toBe("/login");
  });
});
