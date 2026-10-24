import type { Company, User } from "@/lib/api/types";

/**
 * Test fixtures for unit tests only (never imported by application code; a convention test
 * checks that). They mirror the shapes the API returns, with obviously fictitious values.
 */
export const TEST_USER: User = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "test.user@example.test",
  full_name: "Test User",
  preferred_language: "so",
};

export function testCompany(overrides: Partial<Company> = {}): Company {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    code: "T1",
    legal_name: "Test Company One Ltd",
    trade_name: "",
    base_currency_code: "USD",
    country_code: "SO",
    timezone: "Africa/Mogadishu",
    fiscal_year_start_month: 7,
    tenant: { id: "33333333-3333-4333-8333-333333333333", name: "Test Business" },
    ...overrides,
  };
}
