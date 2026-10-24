import type { ReactNode } from "react";

import { Brand } from "@/components/Brand";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { StatusPanel } from "@/components/StatusPanel";
import { getSystemStatus } from "@/lib/health";
import { getMessages } from "@/lib/i18n";
import { getRequestLocale } from "@/lib/i18n/server";

/** Public pages (sign in, password reset): centred card, language switch, system status. */
export default async function AuthLayout({ children }: { children: ReactNode }) {
  const t = getMessages(await getRequestLocale());
  const status = await getSystemStatus(process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000");

  return (
    <div className="auth-page">
      <header className="auth-top">
        <Brand name={t.common.appName} href="/login" />
        <LanguageSwitcher />
      </header>
      <main id="main-content" className="auth-main">
        {children}
      </main>
      <footer className="auth-footer">
        <StatusPanel status={status} messages={t.status} />
      </footer>
    </div>
  );
}
