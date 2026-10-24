import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/LoginForm";
import { getMessages } from "@/lib/i18n";
import { getRequestLocale } from "@/lib/i18n/server";
import { safeNextPath } from "@/lib/redirects";

export async function generateMetadata(): Promise<Metadata> {
  const t = getMessages(await getRequestLocale());
  return { title: `${t.auth.login.title} · ${t.common.appName}` };
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  return (
    <LoginForm
      next={safeNextPath(first(params.next))}
      expired={first(params.reason) === "expired"}
    />
  );
}
