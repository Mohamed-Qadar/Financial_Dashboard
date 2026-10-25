"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusPanel } from "@/components/StatusPanel";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Monogram } from "@/components/ui/Monogram";
import { Chip, EmptyState, PageHeader, Skeleton } from "@/components/ui/States";
import { useCompany } from "@/lib/company/CompanyProvider";
import { companyDisplayName, countryName, currencyName, initials, monthName } from "@/lib/format";
import { getSystemStatus, type SystemStatus } from "@/lib/health";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { useUser } from "@/lib/session/SessionProvider";

function QuickAction({ href, icon, title, hint }: { href: string; icon: IconName; title: string; hint: string }) {
  return (
    <li>
      <Link href={href} className="quick-action">
        <span className="quick-action-icon">
          <Icon name={icon} size={18} />
        </span>
        <span className="quick-action-text">
          <span className="quick-action-title">{title}</span>
          <span className="quick-action-hint">{hint}</span>
        </span>
        <Icon name="chevronRight" size={16} />
      </Link>
    </li>
  );
}

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

  const name = companyDisplayName(company);
  const userName = user.full_name.trim() || user.email;
  const facts: { label: string; value: string; mono?: boolean }[] = [
    { label: t.home.legalName, value: company.legal_name },
    ...(company.trade_name.trim() ? [{ label: t.home.tradeName, value: name }] : []),
    { label: t.home.code, value: company.code, mono: true },
    { label: t.companies.business, value: company.tenant.name },
    {
      label: t.home.baseCurrency,
      value: `${currencyName(locale, company.base_currency_code)} (${company.base_currency_code})`,
    },
    { label: t.home.country, value: countryName(locale, company.country_code) },
    { label: t.home.timezone, value: company.timezone },
    { label: t.home.fiscalYearStart, value: monthName(locale, company.fiscal_year_start_month) },
  ];

  return (
    <>
      <PageHeader
        eyebrow={company.tenant.name}
        leading={<Monogram id={company.id} name={name} size="xl" />}
        title={name}
        description={t.home.welcome(userName)}
        meta={
          <>
            <Chip>{company.code}</Chip>
            <Chip>{company.base_currency_code}</Chip>
            <Chip>{countryName(locale, company.country_code)}</Chip>
          </>
        }
        actions={
          <ButtonLink href="/select-company" icon="swap">
            {t.topbar.switchCompany}
          </ButtonLink>
        }
      />

      <div className="overview-grid">
        <div className="overview-main">
          <Card title={t.home.companyDetails}>
            <dl className="fact-grid">
              {facts.map((fact) => (
                <div key={fact.label} className="fact">
                  <dt>{fact.label}</dt>
                  <dd className={fact.mono ? "tabular" : undefined}>{fact.value}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card>
            <EmptyState icon="layers" title={t.home.modulesTitle}>
              {t.home.modulesBody}
            </EmptyState>
          </Card>
        </div>

        <div className="overview-side">
          <Card title={t.home.signedInAs}>
            <div className="person">
              <span className="user-avatar" data-size="lg" aria-hidden="true">
                {initials(user.full_name, user.email)}
              </span>
              <div className="person-text">
                {user.full_name.trim() ? <p className="person-name">{user.full_name}</p> : null}
                <p className="person-email">{user.email}</p>
              </div>
            </div>
          </Card>
          <Card title={t.home.quickActions}>
            <ul role="list" className="quick-actions">
              <QuickAction href="/select-company" icon="swap" title={t.topbar.switchCompany} hint={t.home.switchCompanyHint} />
              <QuickAction href="/account" icon="lock" title={t.account.changePassword} hint={t.home.changePasswordHint} />
            </ul>
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
      </div>
    </>
  );
}
