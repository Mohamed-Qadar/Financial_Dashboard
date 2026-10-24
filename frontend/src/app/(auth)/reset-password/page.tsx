import type { Metadata } from "next";

import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";
import { getMessages } from "@/lib/i18n";
import { getRequestLocale } from "@/lib/i18n/server";

// The path is fixed by the backend's e-mail (FRONTEND_BASE_URL/reset-password?uid=…&token=…).
// The token is read in the browser only; the server render never looks at the query string.
export async function generateMetadata(): Promise<Metadata> {
  const t = getMessages(await getRequestLocale());
  return { title: `${t.auth.reset.title} · ${t.common.appName}` };
}

export default function ResetPasswordPage() {
  return <ResetPasswordForm />;
}
