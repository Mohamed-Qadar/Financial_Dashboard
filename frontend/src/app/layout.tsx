import type { Metadata } from "next";
import type { ReactNode } from "react";

import { getMessages } from "@/lib/i18n";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { getRequestLocale } from "@/lib/i18n/server";

import "./globals.css";

export const metadata: Metadata = {
  title: "Somali ERP",
  description: "Business management for Somali companies",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await getRequestLocale();
  const t = getMessages(locale);

  return (
    <html lang={locale}>
      <body>
        <a className="skip-link" href="#main-content">
          {t.common.skipToContent}
        </a>
        <LocaleProvider locale={locale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
