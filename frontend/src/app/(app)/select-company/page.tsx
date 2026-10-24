import type { Metadata } from "next";

import { CompanyPicker } from "@/components/company/CompanyPicker";
import { AppShell } from "@/components/shell/AppShell";
import { getMessages } from "@/lib/i18n";
import { getRequestLocale } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = getMessages(await getRequestLocale());
  return { title: `${t.companies.selectTitle} · ${t.common.appName}` };
}

export default async function SelectCompanyPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  return (
    <AppShell company={null}>
      <CompanyPicker notice={params.notice === "unavailable" ? "unavailable" : undefined} auto={params.auto === "1"} />
    </AppShell>
  );
}
