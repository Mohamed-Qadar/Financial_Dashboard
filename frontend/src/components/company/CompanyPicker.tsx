"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { FormError } from "@/components/auth/FormError";
import { Alert } from "@/components/ui/Alert";
import { Icon } from "@/components/ui/Icon";
import { Monogram } from "@/components/ui/Monogram";
import { Spinner } from "@/components/ui/Spinner";
import { Chip, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/States";
import { companies } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { Company } from "@/lib/api/types";
import { companyDisplayName, currencyName, monthName } from "@/lib/format";
import type { Locale, Messages } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { rememberedCompany } from "@/lib/session/companyMemory";
import { useSession } from "@/lib/session/SessionProvider";

type State =
  | { status: "loading" }
  | { status: "ready"; items: Company[] }
  | { status: "error"; error: unknown };

interface Group {
  tenantId: string;
  tenant: string;
  items: Company[];
}

function groupByTenant(items: Company[]): Group[] {
  const groups = new Map<string, Group>();
  for (const company of items) {
    const group = groups.get(company.tenant.id) ?? { tenantId: company.tenant.id, tenant: company.tenant.name, items: [] };
    group.items.push(company);
    groups.set(company.tenant.id, group);
  }
  return [...groups.values()];
}

const noSubscription = () => () => undefined;

/**
 * Companies the user may open, grouped by business (tenant). Opening one records the switch
 * (audited) and goes to `/c/<id>`. With `auto` (straight after login) and exactly one
 * company, it is opened directly. Everything shown comes from `GET /api/v1/companies/`.
 */
export function CompanyPicker({ notice, auto }: { notice?: "unavailable"; auto: boolean }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const { handleAuthError } = useSession();
  const [state, setState] = useState<State>({ status: "loading" });
  const [opening, setOpening] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const autoOpened = useRef(false);
  // This tab's last company (see companyMemory): highlighted, never used for access.
  const lastOpened = useSyncExternalStore(noSubscription, rememberedCompany, () => null);

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

  const groups = state.status === "ready" ? groupByTenant(state.items) : [];

  return (
    <div className="picker">
      <PageHeader
        eyebrow={t.nav.workspace}
        title={t.companies.selectTitle}
        description={t.companies.selectIntro}
        meta={
          state.status === "ready" && state.items.length > 0 ? (
            <>
              <Chip icon="building">{t.companies.companyCount(state.items.length)}</Chip>
              <Chip icon="layers">{t.companies.businessCount(groups.length)}</Chip>
            </>
          ) : null
        }
      />

      {notice === "unavailable" ? <Alert tone="warning">{t.companies.unavailable}</Alert> : null}
      <FormError error={failure} />

      {state.status === "loading" ? (
        <div className="picker-grid" aria-busy="true" aria-label={t.common.loading}>
          {[0, 1, 2].map((key) => (
            <div key={key} className="company-card" data-skeleton>
              <div className="company-card-head">
                <span className="ui-monogram" data-tone="slate" />
                <div className="company-card-titles">
                  <Skeleton width="medium" />
                  <Skeleton width="short" />
                </div>
              </div>
              <Skeleton />
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
        groups.map((group) => (
          <section key={group.tenantId} className="picker-group" aria-labelledby={`business-${group.tenantId}`}>
            <header className="picker-group-head">
              <Monogram id={group.tenantId} name={group.tenant} size="sm" />
              <div>
                <p className="ui-eyebrow">{t.companies.business}</p>
                <h2 id={`business-${group.tenantId}`} className="picker-group-title">
                  {group.tenant}
                </h2>
              </div>
              <span className="ui-badge">{t.companies.companyCount(group.items.length)}</span>
            </header>
            <ul role="list" className="picker-grid">
              {group.items.map((company) => (
                <li key={company.id}>
                  <CompanyCard
                    company={company}
                    locale={locale}
                    t={t}
                    lastOpened={company.id === lastOpened}
                    opening={opening === company.id}
                    disabled={opening !== null && opening !== company.id}
                    onOpen={() => void open(company)}
                  />
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

function CompanyCard({
  company,
  locale,
  t,
  lastOpened,
  opening,
  disabled,
  onOpen,
}: {
  company: Company;
  locale: Locale;
  t: Messages;
  lastOpened: boolean;
  opening: boolean;
  disabled: boolean;
  onOpen: () => void;
}) {
  const name = companyDisplayName(company);
  const showLegalName = company.trade_name.trim() !== "" && company.legal_name !== name;
  return (
    <article className="company-card" data-busy={opening || undefined}>
      <div className="company-card-head">
        <Monogram id={company.id} name={name} size="lg" />
        <div className="company-card-titles">
          <h3 className="company-card-name">{name}</h3>
          {showLegalName ? <p className="company-card-legal">{company.legal_name}</p> : null}
        </div>
        {lastOpened ? (
          <span className="ui-badge" data-tone="info">
            {t.companies.lastOpened}
          </span>
        ) : null}
      </div>
      <dl className="company-card-facts">
        <div>
          <dt>{t.home.code}</dt>
          <dd className="tabular">{company.code}</dd>
        </div>
        <div>
          <dt>{t.companies.currencyShort}</dt>
          <dd title={currencyName(locale, company.base_currency_code)}>{company.base_currency_code}</dd>
        </div>
        <div>
          <dt>{t.companies.fiscalYearShort}</dt>
          <dd>{monthName(locale, company.fiscal_year_start_month)}</dd>
        </div>
      </dl>
      <button
        type="button"
        className="company-card-action"
        onClick={onOpen}
        disabled={disabled || opening}
        aria-busy={opening || undefined}
        aria-label={`${t.companies.openCompany}: ${name}`}
      >
        <span>{opening ? t.companies.opening : t.companies.openCompany}</span>
        {opening ? <Spinner /> : <Icon name="arrowRight" size={16} />}
      </button>
    </article>
  );
}
