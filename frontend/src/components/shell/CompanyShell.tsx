"use client";

import type { ReactNode } from "react";

import { useCompany } from "@/lib/company/CompanyProvider";

import { AppShell } from "./AppShell";

export function CompanyShell({ children }: { children: ReactNode }) {
  return <AppShell company={useCompany()}>{children}</AppShell>;
}
