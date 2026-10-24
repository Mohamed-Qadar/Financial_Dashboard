import { describe, expect, it } from "vitest";

import { getMessages } from "@/lib/i18n";

import { ApiError } from "./errors";
import { errorMessage } from "./messages";

const en = getMessages("en");
const so = getMessages("so");

describe("errorMessage", () => {
  it("uses the UI language, not the backend's English text", () => {
    const error = new ApiError(400, "invalid_credentials", "Invalid email or password.");
    expect(errorMessage(error, en)).toBe("Incorrect email or password.");
    expect(errorMessage(error, so)).toBe("Iimaylka ama erayga sirta ah waa khalad.");
  });

  it("tells how long to wait when throttled", () => {
    const error = new ApiError(429, "throttled", "x", undefined, undefined, 61);
    expect(errorMessage(error, en)).toBe("Too many attempts. Try again in 2 minutes.");
  });

  it("falls back to a generic message", () => {
    expect(errorMessage(new ApiError(418, "teapot", "x"), en)).toBe(en.errors.unknown);
    expect(errorMessage(new Error("boom"), en)).toBe(en.errors.unknown);
    expect(errorMessage(new ApiError(400, "throttledWait", "x"), en)).toBe(en.errors.unknown);
  });
});
