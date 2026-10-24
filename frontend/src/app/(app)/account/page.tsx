import type { Metadata } from "next";

import { AccountView } from "@/components/account/AccountView";
import { AppShell } from "@/components/shell/AppShell";
import { getMessages } from "@/lib/i18n";
import { getRequestLocale } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = getMessages(await getRequestLocale());
  return { title: `${t.account.title} · ${t.common.appName}` };
}

/** User-level page: not tied to a company, so it has no /c/<id>/ prefix. */
export default function AccountPage() {
  return (
    <AppShell company={null}>
      <AccountView />
    </AppShell>
  );
}
