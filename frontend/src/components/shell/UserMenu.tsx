"use client";

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
      trigger={
        <>
          <span className="shell-avatar" aria-hidden="true">
            {initials(user.full_name, user.email)}
          </span>
          <span className="shell-user-name">{name}</span>
          <span className="visually-hidden">{t.topbar.userMenu}</span>
        </>
      }
    >
      <MenuNote>
        <span className="shell-user-email">{user.email}</span>
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
