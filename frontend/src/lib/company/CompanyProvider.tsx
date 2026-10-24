"use client";

import { useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { ErrorState, PageLoading } from "@/components/ui/States";
import { companies } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { Company } from "@/lib/api/types";
import { rememberCompany } from "@/lib/session/companyMemory";
import { useSession } from "@/lib/session/SessionProvider";
import { isUuid } from "@/lib/uuid";

export const UNAVAILABLE_NOTICE = "/select-company?notice=unavailable";

const CompanyContext = createContext<Company | null>(null);

/**
 * The active company comes from the URL (`/c/<companyId>/…`), one per browser tab. It is
 * loaded with `GET /api/v1/company/` + `X-Company-ID`, i.e. the server checks membership and
 * status before anything is shown. 404 (no access, unknown, inactive) → company picker.
 */
export function CompanyProvider({ companyId, children }: { companyId: string; children: ReactNode }) {
  const router = useRouter();
  const { handleAuthError } = useSession();
  // Results are tagged with the id they belong to, so a different id in the URL shows the
  // loading state until its own company has been verified (no stale company is ever shown).
  const [loaded, setLoaded] = useState<{ id: string; company: Company } | null>(null);
  const [failed, setFailed] = useState<{ id: string; error: unknown } | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!isUuid(companyId)) {
      router.replace(UNAVAILABLE_NOTICE);
      return;
    }
    const controller = new AbortController();
    companies
      .active(companyId, controller.signal)
      .then((company) => {
        rememberCompany(company.id);
        setLoaded({ id: companyId, company });
      })
      .catch((failure: unknown) => {
        if (controller.signal.aborted || handleAuthError(failure)) return;
        if (isApiError(failure, "not_found") || isApiError(failure, "company_required")) {
          router.replace(UNAVAILABLE_NOTICE);
          return;
        }
        setFailed({ id: companyId, error: failure });
      });
    return () => controller.abort();
  }, [companyId, attempt, handleAuthError, router]);

  const retry = useCallback(() => {
    setFailed(null);
    setAttempt((value) => value + 1);
  }, []);

  const company = loaded?.id === companyId ? loaded.company : null;
  if (failed?.id === companyId && company === null) {
    return <ErrorState error={failed.error} onRetry={retry} />;
  }
  if (company === null) return <PageLoading />;
  return <CompanyContext.Provider value={company}>{children}</CompanyContext.Provider>;
}

/** A fixed company for the development UI preview only (no API call, grants nothing). */
export function StaticCompanyProvider({ company, children }: { company: Company; children: ReactNode }) {
  return <CompanyContext.Provider value={company}>{children}</CompanyContext.Provider>;
}

/** The verified active company; only inside <CompanyProvider>. */
export function useCompany(): Company {
  const company = useContext(CompanyContext);
  if (company === null) throw new Error("useCompany() must be used inside <CompanyProvider>.");
  return company;
}

/** The active company if the page is company-scoped, else null (e.g. account page). */
export function useOptionalCompany(): Company | null {
  return useContext(CompanyContext);
}
