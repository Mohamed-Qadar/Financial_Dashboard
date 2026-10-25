"use client";

import { Icon } from "@/components/ui/Icon";
import { Menu, MenuItem, MenuLink, MenuNote } from "@/components/ui/Menu";
import { initials } from "@/lib/format";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { useSession, useUser } from "@/lib/session/SessionProvider";

import { useShellNotice } from "./ShellNotice";

export function UserMenu() {
  const { t } = useI18n();
  const user = useUser();
  const { signOut } = useSession();
  const notify = useShellNotice();
  const name = user.full_name.trim() || user.email;

  return (
    <Menu
      label={t.topbar.userMenu}
      buttonClassName="user-button"
      trigger={
        <>
          <span className="user-avatar" aria-hidden="true">
            {initials(user.full_name, user.email)}
          </span>
          <span className="user-text">
            <span className="user-name">{name}</span>
            <span className="user-email">{user.email}</span>
          </span>
          <Icon name="chevronDown" size={16} />
          <span className="visually-hidden">{t.topbar.userMenu}</span>
        </>
      }
    >
      <MenuNote>
        <span className="menu-user-name">{name}</span>
        <span className="menu-user-email">{user.email}</span>
      </MenuNote>
      <MenuLink href="/account" icon="user">
        {t.topbar.accountSettings}
      </MenuLink>
      <MenuItem icon="logout" onSelect={() => signOut().catch(notify)}>
        {t.topbar.signOut}
      </MenuItem>
    </Menu>
  );
}
