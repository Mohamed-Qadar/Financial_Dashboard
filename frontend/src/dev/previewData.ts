/**
 * PREVIEW DATA — not real data.
 *
 * Fictitious records for the development-only UI preview (src/app/ui-preview). Never import
 * this from application code: tests/conventions fail if anything outside src/dev and
 * src/app/ui-preview does. Contains no amounts, balances or transactions.
 */
import type { Company, User } from "@/lib/api/types";

export const PREVIEW_USER: User = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "preview.user@example.test",
  full_name: "Preview User",
  preferred_language: "so",
};

export const PREVIEW_COMPANY: Company = {
  id: "00000000-0000-4000-8000-000000000002",
  code: "PREVIEW",
  legal_name: "Preview Company Ltd (example)",
  trade_name: "Preview Company",
  base_currency_code: "USD",
  country_code: "SO",
  timezone: "Africa/Mogadishu",
  fiscal_year_start_month: 1,
  tenant: { id: "00000000-0000-4000-8000-000000000003", name: "Preview Business (example)" },
};
