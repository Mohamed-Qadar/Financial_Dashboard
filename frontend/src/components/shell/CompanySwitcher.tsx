"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { Menu, MenuGroup, MenuItem, MenuNote } from "@/components/ui/Menu";
import { Monogram } from "@/components/ui/Monogram";
import { Spinner } from "@/components/ui/Spinner";
import { companies } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/messages";
import type { Company } from "@/lib/api/types";
import { companyDisplayName } from "@/lib/format";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { useSession } from "@/lib/session/SessionProvider";

import { useShellNotice } from "./ShellNotice";

type ListState =
  | { status: "idle" | "loading" }
  | { status: "ready"; items: Company[] }
  | { status: "error"; error: unknown };

function byTenant(items: Company[]): [string, Company[]][] {
  const groups = new Map<string, Company[]>();
  for (const company of items) {
    const key = company.tenant.name;
    groups.set(key, [...(groups.get(key) ?? []), company]);
  }
  return [...groups.entries()];
}

/**
 * Active-company switcher at the top of the sidebar. The list comes from
 * `GET /api/v1/companies/` (loaded when the menu opens). Choosing a company records the
 * switch (`POST /api/v1/company/select/`, audited) and navigates to its URL; the server
 * verifies that URL again on every request.
 */
export function CompanySwitcher({ active, compact = false }: { active: Company | null; compact?: boolean }) {
  const { t } = useI18n();
  const router = useRouter();
  const { handleAuthError } = useSession();
  const notify = useShellNotice();
  const [list, setList] = useState<ListState>({ status: "idle" });

  function load() {
    if (list.status === "loading" || list.status === "ready") return;
    setList({ status: "loading" });
    companies
      .list()
      .then((items) => setList({ status: "ready", items }))
      .catch((error: unknown) => {
        if (!handleAuthError(error)) setList({ status: "error", error });
      });
  }

  async function choose(company: Company) {
    if (company.id === active?.id) return;
    try {
      await companies.select(company.id);
      router.push(`/c/${company.id}`);
    } catch (error) {
      if (!handleAuthError(error)) notify(error);
    }
  }

  if (active === null) {
    return (
      <Link href="/select-company" className="workspace-card" title={compact ? t.topbar.selectCompany : undefined}>
        <span className="workspace-empty-icon">
          <Icon name="building" size={18} />
        </span>
        <span className={compact ? "visually-hidden" : "workspace-text"}>
          <span className="workspace-name">{t.topbar.selectCompany}</span>
          <span className="workspace-tenant">{t.companies.noCompany}</span>
        </span>
      </Link>
    );
  }

  const name = companyDisplayName(active);
  return (
    <Menu
      label={t.topbar.switchCompany}
      align="start"
      onOpen={load}
      buttonClassName="workspace-card"
      trigger={
        <>
          <Monogram id={active.id} name={name} />
          <span className={compact ? "visually-hidden" : "workspace-text"}>
            <span className="visually-hidden">{t.topbar.activeCompany}: </span>
            <span className="workspace-name">{name}</span>
            <span className="workspace-tenant">{active.tenant.name}</span>
          </span>
          {!compact ? <Icon name="chevronsUpDown" size={16} /> : null}
        </>
      }
    >
      {list.status === "ready" ? (
        byTenant(list.items).map(([tenant, items]) => (
          <MenuGroup key={tenant} label={tenant}>
            {items.map((company) => (
              <MenuItem key={company.id} checked={company.id === active.id} onSelect={() => void choose(company)}>
                {companyDisplayName(company)} <span className="ui-menu-item-meta">{company.code}</span>
              </MenuItem>
            ))}
          </MenuGroup>
        ))
      ) : list.status === "error" ? (
        <MenuNote>{errorMessage(list.error, t)}</MenuNote>
      ) : (
        <MenuNote>
          <Spinner label={t.common.loading} />
        </MenuNote>
      )}
      <MenuItem icon="swap" onSelect={() => router.push("/select-company")}>
        {t.nav.companies}
      </MenuItem>
    </Menu>
  );
}
