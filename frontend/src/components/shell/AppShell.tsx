"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { Brand } from "@/components/Brand";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Icon, type IconName } from "@/components/ui/Icon";
import type { Company } from "@/lib/api/types";
import type { Messages } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { DESKTOP_QUERY, useMediaQuery } from "@/lib/useMediaQuery";
import { usePersistentFlag } from "@/lib/usePersistentFlag";

import { CompanySwitcher } from "./CompanySwitcher";
import { ShellNoticeProvider } from "./ShellNotice";
import { UserMenu } from "./UserMenu";

const COLLAPSED_KEY = "erp.sidebarCollapsed";
const SIDEBAR_ID = "app-sidebar";

interface NavItem {
  href: string;
  label: keyof Messages["nav"];
  icon: IconName;
  exact?: boolean;
}

/** Only pages that exist. Module pages are added by the milestones that build them. */
function navigation(company: Company | null): NavItem[] {
  return [
    ...(company ? [{ href: `/c/${company.id}`, label: "overview", icon: "home", exact: true } as NavItem] : []),
    { href: "/select-company", label: "companies", icon: "building" },
    { href: "/account", label: "account", icon: "user" },
  ];
}

function isActive(pathname: string, item: NavItem): boolean {
  return item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
}

/**
 * Authenticated layout: collapsible sidebar (desktop ≥ 1024px), off-canvas drawer with
 * Escape/overlay to close on smaller screens, compact top bar with company switcher,
 * language switch and user menu. The collapsed state is a per-browser preference.
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
  const toggleRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);

  const closeDrawer = useCallback((returnFocus: boolean) => {
    setDrawerPath(null);
    if (returnFocus) toggleRef.current?.focus();
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

  function onToggle() {
    if (isDesktop) {
      setCollapsed(!collapsed);
    } else {
      setDrawerPath(drawerOpen ? null : pathname);
    }
  }

  const expanded = isDesktop ? !collapsed : drawerOpen;
  const toggleLabel = isDesktop
    ? collapsed
      ? t.nav.expand
      : t.nav.collapse
    : drawerOpen
      ? t.nav.closeMenu
      : t.nav.openMenu;
  const compact = isDesktop && collapsed;
  const modalDrawer = !isDesktop && drawerOpen;

  return (
    <ShellNoticeProvider>
      <div className="shell" data-collapsed={compact || undefined} data-drawer-open={drawerOpen || undefined}>
        <div
          id={SIDEBAR_ID}
          ref={sidebarRef}
          className="shell-sidebar"
          inert={!isDesktop && !drawerOpen ? true : undefined}
        >
          <div className="shell-sidebar-brand">
            <Brand name={t.common.appName} href={company ? `/c/${company.id}` : "/select-company"} compact={compact} />
          </div>
          <nav aria-label={t.nav.main}>
            <ul role="list" className="shell-nav">
              {navigation(company).map((item) => {
                const label = t.nav[item.label];
                const active = isActive(pathname, item);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="shell-nav-link"
                      aria-current={active ? "page" : undefined}
                      title={compact ? label : undefined}
                    >
                      <Icon name={item.icon} size={18} />
                      <span className={compact ? "visually-hidden" : undefined}>{label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>
        {modalDrawer ? <div className="shell-overlay" aria-hidden="true" onClick={() => closeDrawer(true)} /> : null}
        <div className="shell-main" inert={modalDrawer ? true : undefined}>
          <header className="shell-topbar">
            <button
              ref={toggleRef}
              type="button"
              className="ui-icon-button"
              aria-controls={SIDEBAR_ID}
              aria-expanded={expanded}
              aria-label={toggleLabel}
              title={toggleLabel}
              onClick={onToggle}
            >
              <Icon name={isDesktop ? (collapsed ? "chevronRight" : "chevronLeft") : "menu"} size={20} />
            </button>
            <CompanySwitcher active={company} />
            <div className="shell-topbar-end">
              <LanguageSwitcher />
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
