/** Shapes returned by the Django API (backend serializers; keep in sync). */

export interface User {
  id: string;
  email: string;
  full_name: string;
  preferred_language: "so" | "en";
}

export interface TenantSummary {
  id: string;
  name: string;
}

export interface Company {
  id: string;
  code: string;
  legal_name: string;
  trade_name: string;
  base_currency_code: string;
  country_code: string;
  timezone: string;
  fiscal_year_start_month: number;
  tenant: TenantSummary;
}

/** `{"error": {...}}` — apps/core/exceptions.py */
export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: unknown;
    request_id?: string;
  };
}
