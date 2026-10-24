import type { Metadata } from "next";

import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { getMessages } from "@/lib/i18n";
import { getRequestLocale } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = getMessages(await getRequestLocale());
  return { title: `${t.auth.forgot.title} · ${t.common.appName}` };
}

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
