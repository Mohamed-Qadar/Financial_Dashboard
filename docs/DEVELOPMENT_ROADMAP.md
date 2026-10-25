# Development Roadmap — Somali ERP

A phase is complete only when **all** its acceptance criteria pass in CI and are demonstrated
locally. The roadmap is a plan, not proof of progress; status is updated as phases close.

**Re-ordered 2026-10-25** (owner decision, [PHASE_3_PLAN.md § 0](PHASE_3_PLAN.md#0-new-mvp-ordering-owner-directive-2026-10-25)):
the MVP is built smallest-sellable-product first — master data, then sales with mobile money,
then inventory, purchasing, accounting close and dashboards. The double-entry posting engine
ships with the first posted document (Phase 4), not with the accounting-close phase.

| Phase | Scope | Status |
|---|---|---|
| 0 | Requirements, architecture, database design, security plan, conventions | Done (draft v0.1) |
| 1 | Scaffold, Docker environment, health checks, test & lint tooling, CI | Done (local) |
| 2 | Auth, tenants, companies, roles/permissions, tenant isolation | In progress — plan in [PHASE_2_PLAN.md](PHASE_2_PLAN.md) |
| 3 | Master data: branches, contacts, units, categories, products, chart of accounts, tax rates, exchange rates | Approved, not started — plan in [PHASE_3_PLAN.md](PHASE_3_PLAN.md) |
| 4 | Sales: quotations/orders, customer invoices and credit notes, inbound payments incl. mobile money; posting engine | Not started |
| 5 | Inventory: warehouses, stock movements, stock ledger, per-warehouse balances, weighted average cost | Not started |
| 6 | Purchasing: purchase orders, goods receipts, supplier bills and debit notes, outbound payments | Not started |
| 7 | Accounting close: manual journals UI, reversals, fiscal periods close, trial balance, financial reports, FX revaluation | Not started |
| 8 | Dashboards and reports for owners | Not started |
| 9 | Hardening and pilot preparation: E2E workflows, security testing, import/export, backup/restore | Not started |
| 10 | Expansion: POS, CRM, integrations, subscriptions, more modules | Not started |

Deferred from Phase 2 (owner decision, 2026-10-25): members and invitation links (milestone 2.6)
and their screens — scheduled after Phase 4, before the pilot. No pilot (and no real
bookkeeping) before Phase 5 closes (decision 16).

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

Scope (reduced 2026-10-25): email/password authentication, registration creating tenant +
owner membership + first company (USD) + default branch, login/logout/session endpoints,
active-company selection (`X-Company-ID`), roles/permissions with seeded templates,
`TenantOwnedModel`, tenant context, separate owner/runtime DB roles, RLS policies, composite
foreign keys, audit log, Somali/English i18n foundations, login, registration and
company-picker screens. Branches CRUD moved to Phase 3 (milestone 3.1); members and
invitation links deferred to after Phase 4, before the pilot.

Acceptance criteria:
- Registration creates tenant, owner membership, company and default branch in one transaction; failure leaves nothing behind (tested). (Default warehouse moved to Phase 5 — decision D9, renumbered 2026-10-25.)
- The web process connects with a database role that is not a superuser and cannot bypass RLS (tested).
- Login rate limiting triggers after N failures (tested). Session cookie is HttpOnly; CSRF enforced on unsafe methods (tested).
- Company without access in `X-Company-ID` → 404; another tenant's object → 404; cross-tenant ID in payload → 400 (tested for every endpoint via shared helper, built in milestone 3.1; milestone 2.9 runs right after 3.1).
- RLS test suite: app role sees zero rows of other tenants and zero rows when no tenant is set.
- Test fails if any `TenantOwnedModel` table lacks an RLS policy.
- Test fails if any API view lacks a declared permission.
- Every role/membership change is audit-logged.

## Phase 3 — Master data
Detailed milestones, decisions and tests: [PHASE_3_PLAN.md](PHASE_3_PLAN.md).

Scope: branches CRUD, contacts (customers/suppliers), units of measure, product categories,
products, chart of accounts with a seeded Somali SME template, tax rates (CRUD only, none
seeded), exchange rates (manual USD → SOS entry), a shared money formatter (SOS in whole
shillings), mobile-first screens for all of it.

Acceptance criteria:
- Every Phase 3 endpoint passes the shared cross-tenant isolation helper (other tenant's id → 404; cross-tenant parent id in payload → 400).
- Master data is archived, never deleted: the runtime role has no `DELETE` on any Phase 3 table and API `DELETE` returns 405 (tested).
- Every new company receives the default chart of accounts in the company-creating transaction; existing companies are backfilled idempotently and tenant-correctly (tested).
- Somali account names stay marked "needs review" until a human (the owner or a Somali accountant) has reviewed them; that review happens before milestone 3.5.
- Prices and rates are `Decimal` end to end; no `FloatField` (global test).
- Every Phase 3 view declares its permission codes; create/update/archive actions are audit-logged.

## Phase 4 — Sales and the posting engine
Scope: quotations/sales orders, customer invoices and credit notes, inbound payments (cash,
bank, mobile money recording) and allocation, and the double-entry engine they need:
journals (cash boxes, bank accounts, mobile wallets), journal entries with balance and
immutability triggers, document sequences, fiscal periods. Invoices post financial effects
only (Dr Receivable / Cr Revenue / Cr Tax); stock effects and COGS arrive in Phase 5
(decision 16).

Acceptance criteria:
- Line, tax and total calculations match a table of worked examples, including SOS and USD rounding.
- Posting assigns numbers `PREFIX-YYYY-NNNNN`; 20 concurrent postings produce 20 unique, gap-free numbers.
- Posting an invoice or payment creates its balanced journal entry in the same transaction; an injected failure in any step leaves no partial rows.
- DB rejects committing an unbalanced posted entry even when the service layer is bypassed (trigger test).
- DB rejects update/delete of posted entries (trigger test).
- Posted invoices cannot be edited or deleted via API (409); credit note flow corrects them.
- The same mobile money reference cannot be recorded twice in a wallet journal.
- Allocations cannot exceed payment amount or invoice balance, including under concurrent requests.
- Multi-currency scenario (USD base, SOS invoice, USD payment) produces the expected ledger lines, including realized FX gain/loss.

## Phase 5 — Inventory
Scope: warehouses (including a default warehouse for each existing and new company) and
warehouse UI, `companies.allow_negative_stock`, stock movements (receipt, delivery,
transfer, adjustment, return), stock ledger, per-warehouse balances, weighted average cost,
opening stock via costed adjustments, and stock effects + COGS for invoices posted from
then on.

Acceptance criteria:
- Stock balance changes only via posting a movement; there is no API to set quantity directly.
- Transfer posts two ledger entries; source and destination balances update atomically.
- Negative stock rejected when the company disallows it; concurrent deliveries of the last unit: exactly one succeeds (test with two DB connections).
- Posted movements are immutable; cancellation creates a reversal movement.
- `verify_stock_balances` command reports zero differences after a randomized test sequence.
- UoM conversion uses Decimal and is tested for rounding.
- Posting an invoice for stockable goods creates the delivery and its stock effects (Dr COGS / Cr Inventory) in the same transaction; an injected failure in any step leaves no partial rows.

## Phase 6 — Purchasing
Scope: purchase orders, goods receipts (stock movements of type `receipt`), supplier bills
and debit notes, outbound payments and allocation. Detailed acceptance criteria are written
in the Phase 6 plan; the Phase 4 rules on numbering, immutability, allocation limits and
same-transaction posting apply to purchasing documents as well.

## Phase 7 — Accounting close and financial reports
Scope: manual journal entries UI, reversals, fiscal period close, trial balance, general
ledger, P&L, balance sheet, AR/AP aging, customer/supplier statements, FX revaluation.

Acceptance criteria:
- Trial balance totals debit = credit for a seeded scenario; P&L and balance sheet match hand-calculated expected values.
- AR aging equals sum of open customer invoice balances; AR control account equals AR subledger.
- Postings into a closed period are rejected.
- FX revaluation criteria are written in the Phase 7 plan.

## Phase 8 — Dashboards and reports
Owner-facing dashboards (daily sales, cash and wallet positions, who owes money, stock
value, profit per branch). Acceptance criteria are written in the Phase 8 plan.

## Phase 9 — Hardening and pilot preparation
Scope: end-to-end tests of full business cycles, security review and dependency audit,
CSV import/export, backup and restore scripts, production Docker setup, monitoring, user
documentation in Somali and English.

Acceptance criteria:
- E2E: register → set up company → buy stock → sell on credit → receive mobile money payment → reports correct.
- Restore of a backup into a fresh environment is performed and documented, with checksums of key reports matching.
- No high/critical findings open from `pip-audit`, `npm audit`, and the security checklist.
- Import of 5,000 products and 1,000 contacts with validation report; invalid rows are rejected without partial import.

## Phase 10 — Expansion
POS (with offline queue), CRM, HR/payroll/leave, subscriptions and billing for tenants,
public API tokens and webhooks, verified provider integrations, manufacturing, projects,
price lists. Each gets its own acceptance criteria before work starts.

## Open decisions

Decisions that need the product owner's input. Defaults in **bold** are what the plan assumes until told otherwise.

| # | Decision | Default assumed | Needed by |
|---|---|---|---|
| 1 | First target region(s) | **Decided:** Federal Republic of Somalia; currencies USD and SOS | — |
| 2 | Default base (functional) currency per company | **Decided:** USD | — |
| 3 | Show SOS amounts with decimals or as whole shillings? | **Whole shillings in UI (minor units 0), stored as NUMERIC(18,2)**; the shared money formatter applies it from milestone 3.2 | Phase 3 |
| 4 | Login identifier | **Decided:** email + password | — |
| 5 | Inventory valuation method | **Weighted average cost** (FIFO later if needed) | Phase 5 |
| 6 | Allow negative stock? | **No, configurable per company** | Phase 5 |
| 7 | Taxes: which sales tax/VAT rules apply to the first customers? | **Decided (2026-10-25):** configurable tax rates, no country-specific logic, none seeded — each company enters its real rates | Phase 4 |
| 8 | Fiscal year | **Calendar year (Jan–Dec), configurable** | Phase 4 |
| 9 | Chart of accounts template for Somali SMEs (who validates it — an accountant?) | **Decided (2026-10-25):** template in [PHASE_3_PLAN.md § 5](PHASE_3_PLAN.md#5-default-somali-sme-chart-of-accounts). Somali account names are AI-drafted and stay marked "needs review" until the owner or a Somali accountant reviews them, before milestone 3.5 | Phase 3 (M3.5) |
| 10 | Hosting: cloud region, on-premise for some customers, or both? Connectivity expectations? | **Cloud-hosted SaaS** | Phase 9 |
| 11 | Who provides and reviews Somali translations? | **Decided:** Claude drafts, Somali strings marked "needs review" until approved by the owner/reviewer; English is the source language | — |
| 12 | Pricing / subscription model and trial | Undecided | Phase 10 |
| 13 | Product name and license (proprietary vs open source) | **Proprietary, private repo** | Before public release |
| 14 | Git hosting | **Decided:** local Git only; no remote or publishing until the owner approves after the whole project is complete | — |
| 15 | MVP phase order | **Decided (2026-10-25):** master data → sales → inventory → purchasing → accounting close → dashboards (this roadmap) | — |
| 16 | Sales before inventory: what does an invoice post in Phase 4? | **Decided (2026-10-25):** financial effects only; stock effects and COGS from Phase 5; no pilot before Phase 5 closes | — |
| 17 | Mobile money providers | **Decided (2026-10-25):** `evc_plus, zaad, sahal, edahab, premier_wallet, other`; one wallet account per provider seeded, USD by default, archivable | — |
