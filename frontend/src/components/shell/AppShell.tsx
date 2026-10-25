"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { Brand } from "@/components/Brand";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Icon, type IconName } from "@/components/ui/Icon";
import type { Company } from "@/lib/api/types";
import { companyDisplayName } from "@/lib/format";
import type { Messages } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { DESKTOP_QUERY, useMediaQuery } from "@/lib/useMediaQuery";
import { usePersistentFlag } from "@/lib/usePersistentFlag";

import { CompanySwitcher } from "./CompanySwitcher";
import { ShellNoticeProvider } from "./ShellNotice";
import { UserMenu } from "./UserMenu";

const COLLAPSED_KEY = "erp.sidebarCollapsed";
const SIDEBAR_ID = "app-sidebar";

type NavLabel = "overview" | "companies" | "account";
type SectionLabel = "sectionMain" | "sectionSettings";

interface NavItem {
  href: string;
  label: NavLabel;
  icon: IconName;
  exact?: boolean;
}

interface NavSection {
  label: SectionLabel;
  items: NavItem[];
}

/** Only pages that exist. Module pages are added by the milestones that build them. */
function navigation(company: Company | null): NavSection[] {
  const main: NavItem[] = [
    ...(company ? [{ href: `/c/${company.id}`, label: "overview", icon: "home", exact: true } as NavItem] : []),
    { href: "/select-company", label: "companies", icon: "building" },
  ];
  return [
    { label: "sectionMain", items: main },
    { label: "sectionSettings", items: [{ href: "/account", label: "account", icon: "user" }] },
  ];
}

function isActive(pathname: string, item: NavItem): boolean {
  return item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
}

interface Crumb {
  label: string;
  href?: string;
}

/** Where the user is: business › company › page (only real records and existing pages). */
function breadcrumbs(company: Company | null, pathname: string, nav: Messages["nav"]): Crumb[] {
  const active = navigation(company)
    .flatMap((section) => section.items)
    .find((item) => isActive(pathname, item));
  const page = active ? [{ label: nav[active.label] }] : [];
  if (!company || active?.label === "companies" || active?.label === "account") return page;
  return [{ label: company.tenant.name }, { label: companyDisplayName(company), href: `/c/${company.id}` }, ...page];
}

/**
 * Authenticated layout.
 * - Sidebar (desktop ≥ 1024px): brand, active-company switcher, grouped navigation, collapse
 *   control; the collapsed state is a per-browser preference.
 * - Smaller screens: the sidebar is an off-canvas drawer (menu button, Escape or overlay
 *   closes it, focus returns to the menu button; the page behind is inert).
 * - Top bar: breadcrumb, language switch, user menu.
 */
export function AppShell({ company, children }: { company: Company | null; children: ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const isDesktop = useMediaQuery(DESKTOP_QUERY);
  const [collapsed, setCollapsed] = usePersistentFlag(COLLAPSED_KEY);
  // The drawer belongs to the page it was opened on: navigating or widening the screen
  // closes it without extra state updates.
  const [drawerPath, setDrawerPath] = useState<string | null>(null);
  const drawerOpen = !isDesktop && drawerPath === pathname;
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);

  const closeDrawer = useCallback((returnFocus: boolean) => {
    setDrawerPath(null);
    if (returnFocus) menuButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!drawerOpen) return;
    sidebarRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closeDrawer(true);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen, closeDrawer]);

  const compact = isDesktop && collapsed;
  const modalDrawer = !isDesktop && drawerOpen;
  const crumbs = breadcrumbs(company, pathname, t.nav);

  return (
    <ShellNoticeProvider>
      <div className="shell" data-collapsed={compact || undefined} data-drawer-open={drawerOpen || undefined}>
        <div
          id={SIDEBAR_ID}
          ref={sidebarRef}
          className="shell-sidebar"
          inert={!isDesktop && !drawerOpen ? true : undefined}
        >
          <div className="sidebar-header">
            <Brand
              name={t.common.appName}
              tagline={t.common.tagline}
              href={company ? `/c/${company.id}` : "/select-company"}
              compact={compact}
            />
            {!isDesktop ? (
              <button
                type="button"
                className="sidebar-icon-button"
                aria-label={t.nav.closeMenu}
                onClick={() => closeDrawer(true)}
              >
                <Icon name="close" size={18} />
              </button>
            ) : null}
          </div>

          <div className="sidebar-workspace">
            {!compact ? <p className="sidebar-label">{t.nav.workspace}</p> : null}
            <CompanySwitcher active={company} compact={compact} />
          </div>

          <nav aria-label={t.nav.main} className="sidebar-nav">
            {navigation(company).map((section) => (
              <div key={section.label} className="sidebar-section">
                {!compact ? <p className="sidebar-label">{t.nav[section.label]}</p> : null}
                <ul role="list" className="sidebar-list">
                  {section.items.map((item) => {
                    const label = t.nav[item.label];
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          className="sidebar-link"
                          aria-current={isActive(pathname, item) ? "page" : undefined}
                          title={compact ? label : undefined}
                        >
                          <Icon name={item.icon} size={18} />
                          <span className={compact ? "visually-hidden" : undefined}>{label}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>

          {isDesktop ? (
            <div className="sidebar-footer">
              <button
                type="button"
                className="sidebar-collapse"
                aria-controls={SIDEBAR_ID}
                aria-expanded={!collapsed}
                aria-label={collapsed ? t.nav.expand : t.nav.collapse}
                title={collapsed ? t.nav.expand : t.nav.collapse}
                onClick={() => setCollapsed(!collapsed)}
              >
                <Icon name={collapsed ? "sidebarExpand" : "sidebarCollapse"} size={18} />
                {!compact ? <span aria-hidden="true">{t.nav.collapseShort}</span> : null}
              </button>
            </div>
          ) : null}
        </div>

        {modalDrawer ? <div className="shell-overlay" aria-hidden="true" onClick={() => closeDrawer(true)} /> : null}

        <div className="shell-main" inert={modalDrawer ? true : undefined}>
          <header className="shell-topbar">
            {!isDesktop ? (
              <button
                ref={menuButtonRef}
                type="button"
                className="ui-icon-button"
                aria-controls={SIDEBAR_ID}
                aria-expanded={drawerOpen}
                aria-label={drawerOpen ? t.nav.closeMenu : t.nav.openMenu}
                onClick={() => setDrawerPath(drawerOpen ? null : pathname)}
              >
                <Icon name="menu" size={20} />
              </button>
            ) : null}
            <nav aria-label={t.nav.breadcrumb} className="shell-breadcrumb">
              <ol role="list">
                {crumbs.map((crumb, index) => {
                  const last = index === crumbs.length - 1;
                  return (
                    <li key={`${index}-${crumb.label}`} data-depth={crumbs.length - 1 - index}>
                      {crumb.href && !last ? (
                        <Link href={crumb.href}>{crumb.label}</Link>
                      ) : (
                        <span aria-current={last ? "page" : undefined}>{crumb.label}</span>
                      )}
                    </li>
                  );
                })}
              </ol>
            </nav>
            <div className="shell-topbar-end">
              <LanguageSwitcher />
              <span className="shell-divider" aria-hidden="true" />
              <UserMenu />
            </div>
          </header>
          <main id="main-content" className="shell-content" tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>
    </ShellNoticeProvider>
  );
}
