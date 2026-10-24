# Development Roadmap — Somali ERP

A phase is complete only when **all** its acceptance criteria pass in CI and are demonstrated
locally. The roadmap is a plan, not proof of progress; status is updated as phases close.

| Phase | Scope | Status |
|---|---|---|
| 0 | Requirements, architecture, database design, security plan, conventions | Done (draft v0.1) |
| 1 | Scaffold, Docker environment, health checks, test & lint tooling, CI | Done (local) |
| 2 | Auth, tenants, companies/branches, roles/permissions, tenant isolation | In progress — plan in [PHASE_2_PLAN.md](PHASE_2_PLAN.md) |
| 3 | Contacts, products, units, warehouses, stock movements | Not started |
| 4 | Sales, purchases, invoices/bills, payment recording | Not started |
| 5 | Double-entry accounting, posting, trial balance, AR/AP, financial reports | Not started |
| 6 | End-to-end workflows, security testing, import/export, backup/restore, pilot prep | Not started |
| 7 | POS, CRM, localization depth, integrations, subscriptions, more modules | Not started |

## Phase 0 — Foundations (documentation)
Acceptance criteria:
- [x] PRODUCT_REQUIREMENTS, ARCHITECTURE, DATABASE_DESIGN, SECURITY, this roadmap, README, CLAUDE.md exist.
- [x] Tenant isolation strategy and posting rules are documented.
- [x] Open decisions listed below.

## Phase 1 — Scaffold
Acceptance criteria:
- [x] `docker compose up` starts PostgreSQL, Django and Next.js; no manual steps besides copying `.env.example`.
- [x] `GET /api/v1/health/` returns `200 {"status": "ok"}` without touching the database.
- [x] `GET /api/v1/health/ready/` returns `200` when the DB answers and `503` when it does not.
- [x] API errors use the documented `{"error": {...}}` format; unknown API routes return JSON 404.
- [x] DRF default permission is `IsAuthenticated`.
- [x] Production settings refuse to start with `DEBUG` on or a missing/insecure secret key.
- [x] OpenAPI schema served at `/api/schema/`.
- [x] Frontend home page shows backend and database status, fetched server-side.
- [x] Backend tests (pytest, real PostgreSQL) and frontend tests (Vitest) pass.
- [x] Ruff, ESLint and TypeScript checks pass.
- [x] CI workflow for lint, tests and frontend build written, and its steps verified locally from a clean copy in Docker (backend with a PostgreSQL service, frontend without generated files). It will first run on GitHub only after the owner approves publishing.
- [x] Custom user model (email, UUID) exists before the first migration.

## Phase 2 — Identity, tenancy and access control
Detailed milestones, decisions and tests: [PHASE_2_PLAN.md](PHASE_2_PLAN.md).

Scope: email/password authentication, registration creating tenant + owner membership +
first company (USD) + default branch, login/logout/session endpoints, active-company selection
(`X-Company-ID`), branches CRUD, members and invitation links, roles/permissions with seeded
templates, `TenantOwnedModel`, tenant context, separate owner/runtime DB roles, RLS policies,
composite foreign keys, audit log, Somali/English i18n foundations, login, registration,
company-picker and branch screens.

Acceptance criteria:
- Registration creates tenant, owner membership, company and default branch in one transaction; failure leaves nothing behind (tested). (Default warehouse moved to Phase 3 — decision D9.)
- The web process connects with a database role that is not a superuser and cannot bypass RLS (tested).
- Login rate limiting triggers after N failures (tested). Session cookie is HttpOnly; CSRF enforced on unsafe methods (tested).
- Company without access in `X-Company-ID` → 404; another tenant's object → 404; cross-tenant ID in payload → 400 (tested for every endpoint via shared helper).
- RLS test suite: app role sees zero rows of other tenants and zero rows when no tenant is set.
- Test fails if any `TenantOwnedModel` table lacks an RLS policy.
- Test fails if any API view lacks a declared permission.
- Every role/membership change is audit-logged.

## Phase 3 — Master data and inventory
Scope: contacts, units of measure, product categories, products, warehouses (including a
default warehouse for each existing and new company) and warehouse UI, stock movements
(receipt, delivery, transfer, adjustment, return), stock ledger, balances, weighted average cost.

Acceptance criteria:
- Stock balance changes only via posting a movement; there is no API to set quantity directly.
- Transfer posts two ledger entries; source and destination balances update atomically.
- Negative stock rejected when the company disallows it; concurrent deliveries of the last unit: exactly one succeeds (test with two DB connections).
- Posted movements are immutable; cancellation creates a reversal movement.
- `verify_stock_balances` command reports zero differences after a randomized test sequence.
- UoM conversion uses Decimal and is tested for rounding.

## Phase 4 — Sales, purchasing and payments
Scope: quotations/sales orders, customer invoices and credit notes, purchase orders, goods
receipts, supplier bills, payments (cash, bank, mobile money recording) and allocation.

Acceptance criteria:
- Line, tax and total calculations match a table of worked examples, including SOS and USD rounding.
- Posting assigns numbers `PREFIX-YYYY-NNNNN`; 20 concurrent postings produce 20 unique, gap-free numbers.
- Posting an invoice for stockable goods creates the delivery and its stock effects in the same transaction; an injected failure in any step leaves no partial rows.
- Posted invoices cannot be edited or deleted via API (409); credit note flow corrects them.
- The same mobile money reference cannot be recorded twice in a wallet journal.
- Allocations cannot exceed payment amount or invoice balance, including under concurrent requests.

## Phase 5 — Accounting and financial reports
Scope: chart of accounts template, journals, fiscal periods, automatic postings for Phase 3–4
documents, manual journal entries, reversals, period close, trial balance, general ledger,
P&L, balance sheet, AR/AP aging, customer/supplier statements.

Acceptance criteria:
- DB rejects committing an unbalanced posted entry even when the service layer is bypassed (trigger test).
- DB rejects update/delete of posted entries (trigger test).
- Trial balance totals debit = credit for a seeded scenario; P&L and balance sheet match hand-calculated expected values.
- AR aging equals sum of open customer invoice balances; AR control account equals AR subledger.
- Postings into a closed period are rejected.
- Multi-currency scenario (USD base, SOS invoice, USD payment) produces the expected ledger lines.

## Phase 6 — Hardening and pilot preparation
Scope: end-to-end tests of full business cycles, security review and dependency audit,
CSV import/export, backup and restore scripts, production Docker setup, monitoring, user
documentation in Somali and English.

Acceptance criteria:
- E2E: register → set up company → buy stock → sell on credit → receive mobile money payment → reports correct.
- Restore of a backup into a fresh environment is performed and documented, with checksums of key reports matching.
- No high/critical findings open from `pip-audit`, `npm audit`, and the security checklist.
- Import of 5,000 products and 1,000 contacts with validation report; invalid rows are rejected without partial import.

## Phase 7 — Expansion
POS (with offline queue), CRM, HR/payroll/leave, subscriptions and billing for tenants,
public API tokens and webhooks, verified provider integrations, manufacturing, projects.
Each gets its own acceptance criteria before work starts.

## Open decisions

Decisions that need the product owner's input. Defaults in **bold** are what the plan assumes until told otherwise.

| # | Decision | Default assumed | Needed by |
|---|---|---|---|
| 1 | First target region(s) | **Decided:** Federal Republic of Somalia; currencies USD and SOS | — |
| 2 | Default base (functional) currency per company | **Decided:** USD | — |
| 3 | Show SOS amounts with decimals or as whole shillings? | **Whole shillings in UI (minor units 0), stored as NUMERIC(18,2)** | Phase 4 |
| 4 | Login identifier | **Decided:** email + password | — |
| 5 | Inventory valuation method | **Weighted average cost** (FIFO later if needed) | Phase 3 |
| 6 | Allow negative stock? | **No, configurable per company** | Phase 3 |
| 7 | Taxes: which sales tax/VAT rules apply to the first customers? | **Configurable tax rates, no country-specific logic** | Phase 4 |
| 8 | Fiscal year | **Calendar year (Jan–Dec), configurable** | Phase 5 |
| 9 | Chart of accounts template for Somali SMEs (who validates it — an accountant?) | **Simple IFRS-for-SMEs-style template** | Phase 5 |
| 10 | Hosting: cloud region, on-premise for some customers, or both? Connectivity expectations? | **Cloud-hosted SaaS** | Phase 6 |
| 11 | Who provides and reviews Somali translations? | **Decided:** Claude drafts, Somali strings marked "needs review" until approved by the owner/reviewer; English is the source language | — |
| 12 | Pricing / subscription model and trial | Undecided | Phase 7 |
| 13 | Product name and license (proprietary vs open source) | **Proprietary, private repo** | Before public release |
| 14 | Git hosting | **Decided:** local Git only; no remote or publishing until the owner approves after the whole project is complete | — |
