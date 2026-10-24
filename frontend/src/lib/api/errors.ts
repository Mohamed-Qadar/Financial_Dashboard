import type { ErrorEnvelope } from "./types";

/** Codes produced by the client itself (no usable response from the API). */
export type ClientErrorCode = "network_error" | "server_error";

/**
 * An API failure. `code` is the backend's language-neutral error code (or a client code),
 * so the UI can show its own Somali/English text instead of the backend's English message.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId?: string,
    readonly details?: unknown,
    readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Field errors of a 400 `validation_error`, e.g. `{"new_password": ["Too short."]}`. */
  fieldErrors(): Record<string, string[]> {
    if (this.code !== "validation_error" || typeof this.details !== "object" || !this.details) {
      return {};
    }
    const result: Record<string, string[]> = {};
    for (const [field, value] of Object.entries(this.details as Record<string, unknown>)) {
      if (Array.isArray(value)) {
        result[field] = value.filter((item): item is string => typeof item === "string");
      }
    }
    return result;
  }
}

function isEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string"
  );
}

function retryAfter(response: Response): number | undefined {
  const value = Number(response.headers.get("Retry-After"));
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

/** Turn a non-2xx response into an ApiError, whether or not it carries the error envelope. */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON (e.g. a proxy error page); handled below.
  }
  if (isEnvelope(body)) {
    const { code, message, details, request_id } = body.error;
    return new ApiError(
      response.status,
      code,
      message,
      request_id ?? response.headers.get("X-Request-ID") ?? undefined,
      details,
      retryAfter(response),
    );
  }
  return new ApiError(
    response.status,
    "server_error",
    `Unexpected response (${response.status}).`,
    response.headers.get("X-Request-ID") ?? undefined,
  );
}

export function isApiError(value: unknown, code?: string): value is ApiError {
  return value instanceof ApiError && (code === undefined || value.code === code);
}
