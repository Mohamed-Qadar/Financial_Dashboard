"use client";

import { useEffect, useState } from "react";

import { StatusPanel } from "@/components/StatusPanel";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/States";
import { useCompany } from "@/lib/company/CompanyProvider";
import { companyDisplayName, countryName, currencyName, monthName } from "@/lib/format";
import { getSystemStatus, type SystemStatus } from "@/lib/health";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { useUser } from "@/lib/session/SessionProvider";

/**
 * Company overview. Shows only what the API returns today (company record, signed-in user,
 * system health). There are no business figures yet, so no KPI cards or charts are drawn;
 * the modules card says so instead of showing placeholder numbers.
 */
export function CompanyHome() {
  const { t, locale } = useI18n();
  const company = useCompany();
  const user = useUser();
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    let active = true;
    // Same origin: Next.js forwards /api/ to the backend.
    void getSystemStatus(window.location.origin).then((value) => active && setStatus(value));
    return () => {
      active = false;
    };
  }, []);

  const name = user.full_name.trim() || user.email;

  return (
    <>
      <PageHeader title={t.home.title} description={t.home.welcome(name)} />
      <div className="home-grid">
        <Card title={t.home.companyDetails}>
          <dl className="ui-details">
            <dt>{t.home.legalName}</dt>
            <dd>{company.legal_name}</dd>
            {company.trade_name.trim() ? (
              <>
                <dt>{t.home.tradeName}</dt>
                <dd>{companyDisplayName(company)}</dd>
              </>
            ) : null}
            <dt>{t.home.code}</dt>
            <dd className="tabular">{company.code}</dd>
            <dt>{t.companies.business}</dt>
            <dd>{company.tenant.name}</dd>
            <dt>{t.home.baseCurrency}</dt>
            <dd>
              {currencyName(locale, company.base_currency_code)} ({company.base_currency_code})
            </dd>
            <dt>{t.home.country}</dt>
            <dd>{countryName(locale, company.country_code)}</dd>
            <dt>{t.home.timezone}</dt>
            <dd>{company.timezone}</dd>
            <dt>{t.home.fiscalYearStart}</dt>
            <dd>{monthName(locale, company.fiscal_year_start_month)}</dd>
          </dl>
        </Card>

        <div className="home-side">
          <Card title={t.home.signedInAs}>
            <dl className="ui-details">
              {user.full_name.trim() ? (
                <>
                  <dt>{t.account.fullName}</dt>
                  <dd>{user.full_name}</dd>
                </>
              ) : null}
              <dt>{t.account.email}</dt>
              <dd>{user.email}</dd>
            </dl>
          </Card>
          <Card title={t.home.quickActions}>
            <div className="ui-button-row">
              <ButtonLink href="/select-company" icon="swap">
                {t.topbar.switchCompany}
              </ButtonLink>
              <ButtonLink href="/account" icon="lock">
                {t.account.changePassword}
              </ButtonLink>
            </div>
          </Card>
          <div className="ui-card">
            {status ? (
              <StatusPanel status={status} messages={t.status} />
            ) : (
              <div className="ui-status" aria-busy="true">
                <p className="ui-card-title">{t.status.title}</p>
                <Skeleton width="medium" />
                <Skeleton width="short" />
              </div>
            )}
          </div>
        </div>

        <Card>
          <EmptyState icon="layers" title={t.home.modulesTitle}>
            {t.home.modulesBody}
          </EmptyState>
        </Card>
      </div>
    </>
  );
}
