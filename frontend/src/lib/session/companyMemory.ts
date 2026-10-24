/**
 * The last company opened **in this browser tab** (sessionStorage), only to offer a
 * "back to company" link on pages outside the company URL. It is never sent as the active
 * company: that always comes from the `/c/<companyId>/` URL. Per tab on purpose, so two tabs
 * on different companies cannot influence each other.
 */
import { isUuid } from "@/lib/uuid";

const KEY = "erp.lastCompanyId";

export function rememberCompany(companyId: string): void {
  try {
    if (isUuid(companyId)) sessionStorage.setItem(KEY, companyId);
  } catch {
    // Storage can be unavailable (private mode); the link is only a convenience.
  }
}

export function rememberedCompany(): string | null {
  try {
    const value = sessionStorage.getItem(KEY);
    return isUuid(value) ? value : null;
  } catch {
    return null;
  }
}

export function clearRememberedCompany(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // Nothing to clear.
  }
}
