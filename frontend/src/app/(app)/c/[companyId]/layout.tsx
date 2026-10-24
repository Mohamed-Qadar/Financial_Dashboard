import type { ReactNode } from "react";

import { CompanyShell } from "@/components/shell/CompanyShell";
import { CompanyProvider } from "@/lib/company/CompanyProvider";

/** Every page under /c/<companyId>/ works in that company (verified by the API). */
export default async function CompanyLayout({
  params,
  children,
}: {
  params: Promise<{ companyId: string }>;
  children: ReactNode;
}) {
  const { companyId } = await params;
  return (
    <CompanyProvider companyId={companyId}>
      <CompanyShell>{children}</CompanyShell>
    </CompanyProvider>
  );
}
