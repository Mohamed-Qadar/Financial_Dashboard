export type ApiState = "ok" | "error" | "unreachable";
export type DatabaseState = "ok" | "unavailable" | "unknown";

export interface SystemStatus {
  api: ApiState;
  database: DatabaseState;
}

const READINESS_PATH = "/api/v1/health/ready/";
// Must exceed the backend's database connect_timeout (5 s), otherwise a database outage
// is misreported as the API being unreachable.
const DEFAULT_TIMEOUT_MS = 8000;

/** Ask the backend readiness endpoint whether the API and its database are working. */
export async function getSystemStatus(
  backendUrl: string,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<SystemStatus> {
  try {
    const response = await fetchImpl(new URL(READINESS_PATH, backendUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (response.ok) {
      return { api: "ok", database: "ok" };
    }
    if (response.status === 503) {
      return { api: "ok", database: "unavailable" };
    }
    return { api: "error", database: "unknown" };
  } catch {
    return { api: "unreachable", database: "unknown" };
  }
}
