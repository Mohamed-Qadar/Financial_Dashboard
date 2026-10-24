"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { FormError } from "@/components/auth/FormError";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/States";
import { companies } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { Company } from "@/lib/api/types";
import { companyDisplayName } from "@/lib/format";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { useSession } from "@/lib/session/SessionProvider";

type State =
  | { status: "loading" }
  | { status: "ready"; items: Company[] }
  | { status: "error"; error: unknown };

function groupByTenant(items: Company[]): { tenant: string; items: Company[] }[] {
  const groups = new Map<string, Company[]>();
  for (const company of items) {
    groups.set(company.tenant.name, [...(groups.get(company.tenant.name) ?? []), company]);
  }
  return [...groups.entries()].map(([tenant, list]) => ({ tenant, items: list }));
}

/**
 * Companies the user may open, grouped by business (tenant). Opening one records the switch
 * (audited) and goes to `/c/<id>`. With `auto` (straight after login) and exactly one
 * company, it is opened directly.
 */
export function CompanyPicker({ notice, auto }: { notice?: "unavailable"; auto: boolean }) {
  const { t } = useI18n();
  const router = useRouter();
  const { handleAuthError } = useSession();
  const [state, setState] = useState<State>({ status: "loading" });
  const [opening, setOpening] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const autoOpened = useRef(false);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    companies
      .list(controller.signal)
      .then((items) => setState({ status: "ready", items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted || handleAuthError(error)) return;
        setState({ status: "error", error });
      });
    return () => controller.abort();
  }, [attempt, handleAuthError]);

  const open = useCallback(
    async (company: Company) => {
      setOpening(company.id);
      setFailure(null);
      try {
        await companies.select(company.id);
        router.push(`/c/${company.id}`);
      } catch (error) {
        setOpening(null);
        if (handleAuthError(error)) return;
        if (isApiError(error, "not_found")) reload();
        setFailure(error);
      }
    },
    [handleAuthError, reload, router],
  );

  useEffect(() => {
    if (auto && !notice && state.status === "ready" && state.items.length === 1 && !autoOpened.current) {
      autoOpened.current = true;
      void open(state.items[0]!);
    }
  }, [auto, notice, state, open]);

  return (
    <>
      <PageHeader title={t.companies.selectTitle} description={t.companies.selectIntro} />
      <div className="picker">
        {notice === "unavailable" ? <Alert tone="warning">{t.companies.unavailable}</Alert> : null}
        <FormError error={failure} />
        {state.status === "loading" ? (
          <div className="picker-grid" aria-busy="true" aria-label={t.common.loading}>
            {[0, 1].map((key) => (
              <div key={key} className="ui-card picker-card">
                <Skeleton width="medium" />
                <Skeleton width="short" />
              </div>
            ))}
          </div>
        ) : state.status === "error" ? (
          <div className="ui-card">
            <ErrorState error={state.error} onRetry={reload} />
          </div>
        ) : state.items.length === 0 ? (
          <div className="ui-card">
            <EmptyState icon="building" title={t.companies.noneTitle}>
              {t.companies.noneBody}
            </EmptyState>
          </div>
        ) : (
          groupByTenant(state.items).map((group) => (
            <section key={group.tenant} className="picker-group" aria-label={`${t.companies.business}: ${group.tenant}`}>
              <h2 className="picker-group-title">{group.tenant}</h2>
              <ul role="list" className="picker-grid">
                {group.items.map((company) => (
                  <li key={company.id} className="ui-card picker-card">
                    <div className="picker-card-text">
                      <p className="picker-card-name">{companyDisplayName(company)}</p>
                      <p className="picker-card-meta">
                        <span className="tabular">{company.code}</span> · {company.base_currency_code}
                        {company.trade_name.trim() ? <> · {company.legal_name}</> : null}
                      </p>
                    </div>
                    <Button
                      variant="secondary"
                      icon="chevronRight"
                      loading={opening === company.id}
                      loadingText={t.companies.opening}
                      disabled={opening !== null && opening !== company.id}
                      onClick={() => void open(company)}
                      aria-label={`${t.companies.open}: ${companyDisplayName(company)}`}
                    >
                      {t.companies.open}
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </>
  );
}
