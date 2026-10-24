/** Typed calls of the existing backend endpoints (no new API contract). */
import { apiRequest, type ClientDeps } from "./client";
import type { Company, User } from "./types";

export const auth = {
  me: (signal?: AbortSignal, deps?: ClientDeps) =>
    apiRequest<User>("/api/v1/auth/me/", { signal }, deps),
  login: (email: string, password: string, deps?: ClientDeps) =>
    apiRequest<User>("/api/v1/auth/login/", { method: "POST", body: { email, password } }, deps),
  logout: (deps?: ClientDeps) => apiRequest<void>("/api/v1/auth/logout/", { method: "POST" }, deps),
  changePassword: (currentPassword: string, newPassword: string, deps?: ClientDeps) =>
    apiRequest<void>(
      "/api/v1/auth/password/change/",
      {
        method: "POST",
        body: { current_password: currentPassword, new_password: newPassword },
      },
      deps,
    ),
  requestPasswordReset: (email: string, deps?: ClientDeps) =>
    apiRequest<void>("/api/v1/auth/password/reset/", { method: "POST", body: { email } }, deps),
  confirmPasswordReset: (uid: string, token: string, newPassword: string, deps?: ClientDeps) =>
    apiRequest<void>(
      "/api/v1/auth/password/reset/confirm/",
      { method: "POST", body: { uid, token, new_password: newPassword } },
      deps,
    ),
};

export const companies = {
  /** Companies the user may open (across tenants). Not company-scoped. */
  list: (signal?: AbortSignal, deps?: ClientDeps) =>
    apiRequest<Company[]>("/api/v1/companies/", { signal }, deps),
  /** The company in the URL, verified by the server against the user's membership. */
  active: (companyId: string, signal?: AbortSignal, deps?: ClientDeps) =>
    apiRequest<Company>("/api/v1/company/", { companyId, signal }, deps),
  /** Records a company switch in the audit log (not needed for access). */
  select: (companyId: string, deps?: ClientDeps) =>
    apiRequest<Company>("/api/v1/company/select/", { method: "POST", companyId }, deps),
};
