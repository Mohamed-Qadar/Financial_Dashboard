import { describe, expect, it } from "vitest";

import { companyDisplayName, countryName, currencyName, initials, monthName } from "./format";

describe("format", () => {
  it("names months in both languages", () => {
    expect(monthName("en", 1)).toBe("January");
    expect(monthName("so", 10)).toBe("Oktoobar");
    expect(monthName("en", 13)).toBe("13");
  });

  it("Somali names do not depend on the runtime's locale data (Chrome has none for Somali)", () => {
    const intl = Intl as unknown as Record<string, unknown>;
    const real = { DisplayNames: intl.DisplayNames, DateTimeFormat: intl.DateTimeFormat };
    // Simulate a browser without Somali data: Intl would answer in English.
    intl.DisplayNames = function () {
      return { of: () => "Somalia" };
    };
    intl.DateTimeFormat = function () {
      return { format: () => "July" };
    };
    try {
      expect(monthName("so", 7)).toBe("Luulyo");
      expect(countryName("so", "SO")).toBe("Soomaaliya");
      expect(currencyName("so", "SOS")).toBe("Shilingka Soomaaliya");
      expect(currencyName("so", "EUR")).toBe("EUR");
    } finally {
      intl.DisplayNames = real.DisplayNames;
      intl.DateTimeFormat = real.DateTimeFormat;
    }
  });

  it("matches Node's CLDR data where Node has it", () => {
    const node = new Intl.DateTimeFormat("so-SO", { month: "long", timeZone: "UTC" });
    for (let month = 1; month <= 12; month += 1) {
      expect(monthName("so", month)).toBe(node.format(new Date(Date.UTC(2024, month - 1, 1))));
    }
  });

  it("names countries and currencies, falling back to the code", () => {
    expect(countryName("en", "SO")).toBe("Somalia");
    expect(currencyName("en", "USD")).toBe("US Dollar");
    expect(currencyName("en", "SOS")).toBe("Somali Shilling");
    expect(countryName("en", "not-a-code")).toBe("not-a-code");
  });

  it("builds avatar initials", () => {
    expect(initials("Hodan Ali", "x@y.so")).toBe("HA");
    expect(initials("", "hodan.ali@example.so")).toBe("HA");
    expect(initials("", "abc@example.so")).toBe("AB");
  });

  it("prefers the trade name", () => {
    expect(companyDisplayName({ trade_name: "Hodan Foods", legal_name: "Hodan Foods Ltd" })).toBe("Hodan Foods");
    expect(companyDisplayName({ trade_name: " ", legal_name: "Hodan Foods Ltd" })).toBe("Hodan Foods Ltd");
  });

  it("documents the SOS trap for later money formatting (ICU uses 0 digits, ISO 4217 says 2)", () => {
    const icuDefault = new Intl.NumberFormat("en", { style: "currency", currency: "SOS" }).resolvedOptions();
    expect(icuDefault.maximumFractionDigits).toBe(0);
  });
});
