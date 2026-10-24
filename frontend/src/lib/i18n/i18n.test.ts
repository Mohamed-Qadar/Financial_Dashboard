import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, getMessages, localeCookie, resolveLocale } from "./index";
import { en } from "./messages/en";
import { reviewStatus, so } from "./messages/so";

/** Every key path of a dictionary, with the kind of value (string or function). */
function shape(value: unknown, prefix = ""): string[] {
  if (typeof value === "string") return [`${prefix}:string`];
  if (typeof value === "function") return [`${prefix}:function`];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    shape(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe("dictionaries", () => {
  it("Somali has exactly the keys of English", () => {
    expect(shape(so).sort()).toEqual(shape(en).sort());
  });

  it("no message is empty", () => {
    for (const dictionary of [en, so]) {
      const empty = shape(dictionary).filter((entry) => {
        const path = entry.split(":")[0]!.split(".");
        const value = path.reduce<unknown>(
          (node, key) => (node as Record<string, unknown>)[key],
          dictionary,
        );
        return typeof value === "string" && value.trim() === "";
      });
      expect(empty).toEqual([]);
    }
  });

  it("Somali drafts stay marked for review until a Somali speaker approves them (D12)", () => {
    expect(reviewStatus).toBe("needs-review");
  });

  it("interpolates values", () => {
    expect(en.home.welcome("Hodan")).toBe("Welcome, Hodan");
    expect(so.home.welcome("Hodan")).toBe("Ku soo dhowow, Hodan");
    expect(en.errors.throttledWait(1)).toContain("1 minute.");
  });
});

describe("locale resolution", () => {
  it("defaults to Somali", () => {
    expect(DEFAULT_LOCALE).toBe("so");
    expect(resolveLocale(undefined)).toBe("so");
    expect(resolveLocale("")).toBe("so");
  });

  it.each(["tr", "EN", "en-US", "so;", "<script>"])("rejects %s", (value) => {
    expect(resolveLocale(value)).toBe("so");
  });

  it("accepts the supported languages", () => {
    expect(resolveLocale("en")).toBe("en");
    expect(getMessages("en").common.retry).toBe("Try again");
  });

  it("stores the choice in a first-party, site-wide cookie", () => {
    expect(localeCookie("en")).toBe("erp_lang=en; Path=/; Max-Age=31536000; SameSite=Lax");
  });
});
