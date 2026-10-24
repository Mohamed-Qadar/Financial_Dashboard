import type { Messages } from "@/lib/i18n";

import { ApiError } from "./errors";

type ErrorCode = Exclude<keyof Messages["errors"], "throttledWait">;

/**
 * The user-facing text for an error, in the UI language. Backend messages are English until
 * milestone 2.7, so the text is chosen by error code; unknown codes get a generic message.
 */
export function errorMessage(error: unknown, t: Messages): string {
  if (!(error instanceof ApiError)) return t.errors.unknown;
  if (error.code === "throttled" && error.retryAfterSeconds) {
    return t.errors.throttledWait(Math.max(1, Math.ceil(error.retryAfterSeconds / 60)));
  }
  if (error.code in t.errors && error.code !== "throttledWait") {
    return t.errors[error.code as ErrorCode] as string;
  }
  return t.errors.unknown;
}
