# Phase 3 Implementation Plan — Master Data

Status: **Approved plan (owner, 2026-10-25).** All ten open questions in § 10 were answered
with the ★ defaults, and P3-D2 is Option A; every ★ option in this document is now binding.
Each milestone is still implemented only after the owner approves it, one at a time.
Language of the owner's review: Turkish summary in chat; this document is the reference.

Two extra conditions set by the owner with the approval:
1. **Somali chart-of-account names are AI-drafted and stay marked "needs review".** They are
   not final; a human (the owner or a Somali accountant) reviews them **before milestone
   3.5** starts.
2. The uncommitted M2.8a frontend work is committed before anything else — done in commit
   `ded9ebf`, before M3.0.

## 0. New MVP ordering (owner directive, 2026-10-25)

The owner redefined the MVP phase ordering around the product's differentiators
(mobile-first, mobile money first-class, USD/SOS dual currency, natural Somali, multi-branch):

| Phase | New scope | Old roadmap scope (for comparison) |
|---|---|---|
| 3 | **Master data**: products, partners (customers/suppliers), branches, chart of accounts | Master data **and** inventory |
| 4 | Sales: quote → order → invoice → payment (incl. mobile money) | Sales, purchasing and payments together |
| 5 | Inventory: stock moves, per-warehouse balances (branch reporting via warehouse → branch), basic valuation | Accounting and reports |
| 6 | Purchasing: supplier orders → bills → payment | Hardening and pilot prep |
| 7 | Accounting close: journals UI, manual entries, trial balance, basic reports, FX revaluation | Expansion |
| 8 | Dashboards and reports | — |
| 9 | Hardening and pilot preparation (old Phase 6, incl. CSV import/export) | — |
| 10 | Expansion: POS, CRM, HR, subscriptions, public API (old Phase 7) | — |

`docs/DEVELOPMENT_ROADMAP.md` still describes the old ordering; milestone 3.0 (docs-only
commit) rewrites it — see the full documentation-delta list in § 9. Note: the double-entry
posting *engine* (journal entries + balance and immutability triggers, document sequences,
fiscal periods, multi-currency entry lines) cannot wait for Phase 7 — it ships **inside
Phase 4** with the first posted document (PRODUCT_REQUIREMENTS FR-7 and rule 6: a posted
document creates its balanced entry in the same transaction). Phase 7 is the accounting
*surface* (manual journals UI, period close, reports), not the engine.

## 1. Current state and prerequisites

Phase 2 milestones done: 2.0, 2.1, 2.2, 2.3a, 2.8a. Not done: 2.3b (registration),
2.4 (roles/permissions), 2.5 (branches CRUD), 2.6 (members/invitations), 2.7 (backend i18n),
2.8b (remaining screens), 2.9 (close). The second M2.8a frontend iteration that was
uncommitted when this plan was written is committed as `ded9ebf`.

Ordering before Phase 3 coding starts:

1. **2.3b registration** — hard prerequisite. Creates tenant + owner membership + company +
   default branch. Under the new ordering it must **not** create a warehouse (moves to
   Phase 5) and not yet seed the chart of accounts (M3.5 adds the seeding hook plus a
   backfill for existing companies).
2. **2.4 roles/permissions** — hard prerequisite. Every Phase 3 endpoint declares
   `module.resource.action` permission codes from day one; the "every view declares a
   permission" test must exist before the first new view.
3. **2.7 backend i18n** — strongly recommended before 3.1 (small, independent since 2.2), so
   every Phase 3 milestone lands with Somali/English catalogs and the completeness test.
4. **2.5 branches CRUD** folds into Phase 3 as milestone 3.1 (branches are master data in the
   new plan; the table exists since 2.3a, so 3.1 is endpoints/screens plus the shared
   isolation test helper every later milestone reuses).
5. **2.6 members/invitations + 2.8b members screens** — deferred to after Phase 4, before the
   pilot. M3.0 amends the roadmap's Phase 2 scope/criteria and marks 2.5/2.6/2.8b/2.9 in
   `PHASE_2_PLAN.md` with this re-scope (it changes an owner-approved plan, hence open
   question 1). **2.9 runs right after M3.1**, when the reduced-scope walkthrough
   (register → log in → pick a company → manage branches) can pass without invitations.

## 2. Decisions (★ = recommended default; owner approval makes them binding)

**P3-D1 — Adopt the new phase numbering and rewrite the docs.**
★ Yes. Milestone 3.0 is a docs-only commit; its full delta list is in § 9. Highlights:
old Phase 3's stock criteria and D9's "default warehouse" → new Phase 5; old Phase 4's
"invoice posting creates stock effects in the same transaction" criterion → new Phase 5
(consequence of P3-D2); old Phase 5's posting-engine criteria (balance + immutability
triggers, gap-free numbering, multi-currency entry lines) → new Phase 4, with only
close/report criteria staying in new Phase 7.

**P3-D2 — Sales (4) before inventory (5): what does an invoice post?**
The documented flow "post customer invoice for stockable goods → delivery + COGS in the
same transaction" (DATABASE_DESIGN § 9) cannot run while stock tables do not exist.
- ★ **A.** Phase 4 posts financial effects only: Dr Receivable / Cr Revenue / Cr Tax;
  payments Dr wallet-or-cash / Cr Receivable with realized FX gain/loss; unallocated
  remainders to customer/supplier advances. Phase 5 extends the same posting service so
  invoices posted *from then on* also write delivery + Dr COGS / Cr Inventory atomically.
  Invoices posted before Phase 5 get no retroactive COGS — acceptable only while data is
  development-only, so **no pilot (and no real bookkeeping) before Phase 5 closes**.
- B. Swap back to inventory-first (old ordering). Safest accounting, delays the owner's
  priority (sales + mobile money).
- C. Phase 4 restricted to service/consumable products. Rejected: target users are shops.

**P3-D3 — tax_rates ships in Phase 3; product default-tax columns wait for Phase 4.**
★ The `tax_rates` table (company-scoped, CRUD only, **no tax math, nothing seeded**)
ships in Phase 3 so the CoA's tax accounts have their consumer defined. The planned
`products.sales_tax_id` / `purchase_tax_id` columns are **deferred to Phase 4**: products
are tenant-level, tax rates are company-level, so a product-level default crosses the scope
boundary (meaningless for a tenant with two companies). Phase 4 picks taxes per document
line and decides then whether a per-company product default is needed. Tax *rates* are an
owner decision (Somali practice varies by city/administration): seeding a wrong rate would
silently corrupt every invoice, so none are seeded.

**P3-D4 — exchange_rates in Phase 3; company_currencies cut.**
★ `exchange_rates` ships in Phase 3: manual daily entry, stored in **one canonical
direction (USD → SOS)** with the inverse derived in the selector (two independent
directional rows could drift out of inverse consistency); one rate per day; corrections
via audited PATCH — harmless because documents copy the rate they used.
`company_currencies` is **cut** until a third currency exists: with only USD and SOS in
`currencies`, validation against the global table is enough. `DATABASE_DESIGN.md` updated.

**P3-D5 — Default chart of accounts (template in § 5).**
★ 39 postable accounts + 7 group accounts, IFRS-for-SMEs shaped, seeded per company inside
the company-creating transaction (and backfilled for existing companies by a data
migration). Names seeded in the tenant's `default_language` from a bilingual template in
code; Somali names are Claude-drafted and marked **needs review** (decision D12 process).
A new column `accounts.system_key varchar(30) NULL` with `UQ (company_id, system_key)`
gives the Phase 4/5 posting services stable handles that survive user renames and
re-codes — including keys for every seeded cash, bank and wallet account, so Phase 4 can
create the matching journals without looking accounts up by editable code/name.

**P3-D6 — Mobile money provider list.**
The directive names *Premier Wallet*; `DATABASE_DESIGN.md` lists `edahab` and not
`premier_wallet`. ★ Reconcile to `evc_plus, zaad, sahal, edahab, premier_wallet, other`
(used by the CoA wallet accounts now and the Phase 4 `journals.mobile_money_provider` CK).
All five wallet accounts are seeded, USD-restricted by default (editable), archivable per
company.

**P3-D7 — Archivability everywhere.**
★ `units_of_measure` and `product_categories` get an `is_active` column (missing in the
original design) so every master-data table archives instead of deleting; the runtime role
gets **no DELETE** on any Phase 3 table; API `DELETE` returns 405; archive/restore are
explicit endpoints.

**P3-D8 — Tenant-level vs company-level scope.**
★ Contacts, products, categories and UoM stay tenant-level (shared across a tenant's
companies, per the Phase 0 design); accounts, tax_rates and exchange_rates are
company-level. Consequence to document and test: a role restricted to one company may
still edit tenant-wide master data — inherent to sharing, acceptable for the MVP.

**P3-D9 — Default units seed.**
★ Seed per tenant at registration (+ backfill): pcs, kg, g, litre, ml, metre — real
conversion units — plus carton and box seeded as **ratio-1 count labels only** (a
tenant-wide fixed carton ratio would be meaningless across products and would corrupt
Phase 5 `quantity_base` conversion; real packaging ratios arrive later as a per-product
mechanism). Owner may add Somali-market units (e.g. *jawaan*/sack, also as count labels).

## 3. Scope

**IN:** branches CRUD (+ shared isolation helper); contacts; units_of_measure;
product_categories; products; accounts + default CoA seeding; tax_rates (CRUD only);
exchange_rates; the shared money formatter (SOS whole-shilling display); mobile-first
screens for all of it; permission codes, audit events, isolation/validation/archive tests
throughout.

**OUT (and where it lands):** warehouses, stock tables, valuation,
`companies.allow_negative_stock` → Phase 5. Journals, journal_entries, document_sequences,
fiscal_periods, payments → Phase 4. Product default-tax columns → Phase 4 (P3-D3).
Price lists → Phase 10 (expansion). Depreciation flows → Phase 7 (accounting close) or
later. company_currencies → cut (P3-D4). CSV import/export → Phase 9 (hardening).
No document numbering in Phase 3 (master-data codes/SKUs are user-supplied).

## 4. Data model

New app `contacts` (the module name `ARCHITECTURE.md` already documents) and new app
`catalog` (UoM, categories, products); `finance` gains accounts, tax_rates and
exchange_rates (ARCHITECTURE.md currently files taxes under catalog — moved to finance
because `tax_rates.account_id` FKs accounts and catalog → finance would invert the
dependency direction; § 9 records the doc delta). Every table inherits `TenantOwnedModel`;
**the same migration** adds RLS (`enable_rls` + `tenant_isolation`), composite FKs,
privilege grants (`revoke_from_app_role(..., "DELETE")`) and the matching
`test_privilege_matrix.py` entry. Column details follow `DATABASE_DESIGN.md` §§ 4 and 7
with the deltas noted in § 2.

| Table (app) | Scope | Composite FKs `(tenant_id, col) → parent(tenant_id, id)` | Key constraints |
|---|---|---|---|
| contacts (contacts) | tenant | — (currency FK is global) | UQ(tenant, code); CK is_customer OR is_supplier; CK credit_limit ≥ 0 |
| units_of_measure (catalog) | tenant | — | UQ(tenant, symbol); CK ratio > 0; one reference unit per category (partial UQ) |
| product_categories (catalog) | tenant | parent_id → self | UQ(tenant, parent, name) `nulls_distinct=False`; cycle check in service |
| products (catalog) | tenant | base_uom_id → units_of_measure; category_id → product_categories | UQ(tenant, sku); partial UQ(tenant, barcode); CK prices ≥ 0; CK product_type |
| accounts (finance) | company | company_id → companies; parent_id → self **plus** `(company_id, parent_id) → accounts(company_id, id)` | UQ(company, id); UQ(company, code); UQ(company, system_key); CK account_type; CK subtype per type (enum in § 5; groups have subtype NULL, postable accounts NOT NULL); parent must be group (service + test) |
| tax_rates (finance) | company | company_id → companies; account_id → accounts **plus** `(company_id, account_id) → accounts(company_id, id)` | UQ(company, name, type_use); CK rate 0–100 |
| exchange_rates (finance) | company | company_id → companies | UQ(company, from, to, effective_date); CK rate > 0; CK from ≠ to |

View scoping: company-scoped views keep `CompanyScopedAPIView`; tenant-level master data
uses a documented marker subclass `TenantScopedAPIView(CompanyScopedAPIView)` — the
`X-Company-ID` header stays mandatory (it is the membership check and, from 2.4, the
permission context); selectors then take `request.tenant`, never filter by company.
A read-only `GET /api/v1/currencies/` is added to the conventions test's explicit
non-company-scoped exemption list.

## 5. Default Somali SME chart of accounts

4-digit codes, five blocks by `account_type`; **(G)** = group (`is_group`, no postings,
subtype NULL). 39 postable accounts + 7 groups. English names below; Somali drafts ship in
the code template (needs review, D12).

Subtype enum (CK per account_type; full list is the M3.0 `DATABASE_DESIGN.md` delta):
asset: `cash, bank, mobile_money, receivable, inventory, supplier_advance, tax,
fixed_asset, other_asset` · liability: `payable, customer_advance, tax, other_liability` ·
equity: `equity` · income: `sales, other_income, fx_gain` · expense: `cogs,
stock_adjustment, operating_expense, fx_loss, other_expense`.

| Code | Name | Type/subtype | system_key / notes |
|---|---|---|---|
| 1000 | Assets (G) | asset | |
| 1100 | Cash & Equivalents (G) | asset | |
| 1110 / 1120 | Cash on Hand – USD / – SOS | asset/cash | `cash_usd` / `cash_sos`; currency-restricted |
| 1130 | Bank Account | asset/bank | `bank`; user adds more |
| 1140 | Mobile Money (G) | asset | |
| 1141–1145 | EVC Plus, Zaad, Sahal, eDahab, Premier Wallet | asset/mobile_money | `wallet_evc_plus` … `wallet_premier_wallet`; USD default; archive unused |
| 1210 | Accounts Receivable (Deyn) | asset/receivable | `ar`; contact required on entry lines |
| 1220 | Staff Advances | asset/other_asset | common in Somali SMEs |
| 1310 | Inventory on Hand | asset/inventory | `inventory`; used from Phase 5 |
| 1410 | Supplier Advances | asset/supplier_advance | `supplier_advance`; contact required |
| 1420 | Tax Receivable | asset/tax | `tax_receivable` |
| 1510 / 1590 | Equipment & Furniture / Accumulated Depreciation | asset/fixed_asset | depreciation flows Phase 7+; 1590 is the contra account by convention |
| 2000 | Liabilities (G) | liability | |
| 2110 | Accounts Payable | liability/payable | `ap`; contact required |
| 2120 | Goods Received Not Invoiced | liability/payable | `grni`; used from Phase 6 |
| 2200 | Customer Advances | liability/customer_advance | `customer_advance`; contact required |
| 2310 | Sales Tax Payable | liability/tax | `sales_tax_payable` |
| 2400 | Loans Payable | liability/other_liability | |
| 3000 | Equity (G) → 3100 Owner's Capital, 3200 Owner's Drawings, 3300 Retained Earnings, 3900 Opening Balance Equity | equity/equity | `retained_earnings` (3300), `opening_balance` (3900) |
| 4000 | Income (G) → 4100 Sales Revenue, 4800 Other Income, 4900 FX Gain | income/sales, other_income, fx_gain | `sales` (4100), `fx_gain` (4900); credit notes post against 4100 |
| 5000 | Expenses (G) → 5100 COGS, 5110 Inventory Adjustments, 5210 Rent, 5220 Salaries & Wages, 5230 Electricity & Water, 5240 Phone & Internet, 5250 Transport & Fuel, 5260 Mobile Money Charges, 5270 Bank Charges, 5290 Miscellaneous, 5900 FX Loss, 5950 Bad Debts | expense | `cogs` (5100), `stock_adjustment` (5110), `fx_loss` (5900); 52xx = operating_expense; 5260 first-class: wallet merchant fees |

Deliberately cut for leanness: sales returns/discount accounts, payroll liabilities,
departments, multiple banks, VAT input/output splits. Dual currency works through journal
entry lines (base debit/credit + transaction currency/amount/rate), not duplicated
accounts; only cash boxes and wallets are currency-restricted. The journal-entry-line
"contact required" rule extends to `customer_advance` and `supplier_advance` subtypes
(M3.0 doc delta; enforced by the Phase 4 posting service) so advance balances are always
attributable to a contact.

Seeding: `apps.finance.services.create_default_accounts(company)` and the catalog unit
seed run inside the company-creating transaction. To keep the documented dependency
direction (registration lives below finance/catalog), they are invoked through a **seeding
hook registry in core**: finance and catalog register their seed functions at app-ready,
and the 2.3b registration service calls the registry (ARCHITECTURE.md delta in § 9).
A reversible, idempotent data migration backfills existing companies. The migration runs
as the owner role, so it must enter the tenant context per tenant via
`apps.core.tenancy` (rule: context changes only through that module) — under a
non-superuser production owner, `FORCE ROW LEVEL SECURITY` would otherwise block it (it
only "just works" locally because the local owner is a superuser). Isolation test
required: seeded rows carry the right tenant/company.

## 6. API surface and permissions

Company-scoped (existing base class): `branches/`, `branches/<id>/`,
`branches/<id>/archive/`, `…/restore/` (M3.1, old 2.5 spec); `accounts/`, `tax-rates/`,
`exchange-rates/` (GET/POST, PATCH; archive where applicable).
Tenant-scoped (marker subclass): `contacts/`, `contacts/<id>/`, `contacts/<id>/archive/`,
`…/restore/`; same shape for `units/`, `product-categories/`, `products/`.
Global read-only: `currencies/`. All under `/api/v1/` with trailing slashes; errors in the
standard envelope. Pagination **20 per page / max 100** — a deliberate mobile-first
tightening of ARCHITECTURE.md's 50/200 default, recorded as a doc delta (§ 9).
Server-side `?q=` search (contacts: name/code/phone; products: name/sku/barcode exact for
scanning; accounts: code/name) plus `is_active`, `is_customer/is_supplier`,
`product_type` filters; stable ordering. Btree indexes `(tenant_id, name)` on contacts
and products; pg_trgm deferred until measured.

Permission codes (enforced once 2.4 lands — a prerequisite, so no stub period):
`organizations.branch.{view,create,update,archive}`,
`contacts.contact.{view,create,update,archive}`,
`catalog.{product,category,uom}.{view,create,update,archive}`,
`finance.{account,tax_rate}.{view,create,update,archive}`,
`finance.exchange_rate.{view,create,update}`.

Audit: new event types in `apps/audit/events.py` per milestone (e.g.
`contacts.contact_created`, `finance.account_archived`), recorded via `record_event()`
inside each operation's transaction. Event names are permanent — the module names above
are final before the first event ships.

## 7. Mobile-first frontend

Reuses the 2.8a shell, API client, i18n and tokens; routes under `/c/[companyId]/`.
Screens: branches, contacts, products (each: search-first single-column card list →
full-screen form), settings lists for UoM/categories/taxes, chart of accounts as an
accordion grouped by account type, "today's rate" one-field screen (USD → SOS; the
inverse is derived, P3-D4). Rules: ≤ 3 required fields per form (rest behind a "More
details" disclosure); card rows with 2–3 facts instead of data tables on phones; one
primary action per screen; debounced server-side search + pagination for weak
connections; usable at 360 px. Money display: `format.ts` has **no money formatter yet**
(its header defers money to later modules) — M3.2 adds one that takes the currency's
minor units explicitly and displays **SOS with 0 fraction digits** (roadmap decision #3;
storage stays NUMERIC(18,2), seeded `minor_units=2` unchanged). Every string in both
`en.ts` and `so.ts` (Somali marked for review). No new dependencies.

## 8. Testing plan (per endpoint unless noted)

1. **Isolation** (shared helper from M3.1): other tenant's id → the same 404 as a random
   UUID; lists never leak; cross-tenant parent id in payload (other tenant's UoM/category/
   account) → 400; `tenant_id`/`company_id` in the body ignored.
2. **DB level:** extend the RLS app-role matrix with one tenant-level (contacts) and one
   company-level (accounts) table; owner-connection FK-violation tests per composite FK.
   `test_rls_catalog.py` covers the new tables automatically (TenantOwnedModel discovery).
3. **Validation:** duplicate code/sku/symbol → 400; CK violations surface as 400; category
   cycles rejected; tax account must belong to the same company and not be a group;
   referencing an archived UoM/category/account → 400; prices/rates as string decimals
   only.
4. **Archive:** archived rows leave default lists (`?include_archived=true` shows them);
   restore works; HTTP DELETE → 405; runtime-role DELETE denied (privilege matrix + real
   app-role connection).
5. **Seeding:** registration yields the full template (39 postable + 7 groups, balanced
   tree, groups marked, system keys unique); backfill migration is idempotent and
   tenant-correct.
6. **Money rules:** no new FloatField (global test already enforces); SOS formatter
   displays whole shillings while USD keeps 2 decimals.

## 9. Milestones (one local commit each; `pg_dump` backup before every migration)

| M | Content |
|---|---|
| 3.0 | **Docs only.** DEVELOPMENT_ROADMAP.md: phase renumbering incl. criteria moves per P3-D1, Phase 2 scope reduced (2.5 → M3.1, 2.6/2.8b pre-pilot), open-decisions "Needed by" column updated (CoA → Phase 3; valuation/negative stock → Phase 5; fiscal year → Phase 4). PHASE_2_PLAN.md: 2.5/2.6/2.8b/2.9 marked with the re-scope. PRODUCT_REQUIREMENTS.md: MVP phase range and "Later (Phase 7+)" heading renumbered. ARCHITECTURE.md: taxes move catalog → finance; seeding hook registry noted; pagination default 20/100. DATABASE_DESIGN.md: accounts.system_key, subtype enum, is_active on UoM/categories, provider enum incl. premier_wallet, company_currencies cut, product tax columns moved to Phase 4, contact-required rule extended to advance subtypes, canonical exchange-rate direction. This plan marked Approved. |
| 3.1 | Branches CRUD (old 2.5 spec: archive not delete, mass-assignment guards) + shared isolation helper + branch screens. **2.9 (Phase 2 close, reduced scope) runs right after.** |
| 3.2 | Contacts: table, CRUD, search/filters, screens. Shared money formatter in `format.ts` (SOS whole shillings). |
| 3.3 | UoM + categories: tables, default-unit seeding (registration + backfill), settings screens |
| 3.4 | Products: table (no tax columns), CRUD, SKU/barcode uniqueness, screens |
| 3.5 | Chart of accounts: table + `system_key`, CoA template + seeding hook registry + backfill, read-mostly screen. **Gate:** starts only after a human (owner or Somali accountant) has reviewed the Somali account names; they stay marked "needs review" until then |
| 3.6 | tax_rates + exchange_rates: tables, CRUD, "today's rate" screen |
| 3.7 | Phase close: isolation sweep, i18n completeness, privilege matrix green, docs updated, Somali/English demo walkthrough |

## 10. Owner questions — answered 2026-10-25: all ★ defaults accepted

Kept as the record of what was decided; the Somali account-name review in question 6 is
tightened by extra condition 1 at the top of this document.

1. Approve the re-scope of approved Phase 2: 2.5 → M3.1, 2.6/2.8b deferred to pre-pilot,
   2.9 closing at reduced scope right after M3.1? ★ Yes.
2. Run 2.7 (backend i18n) before Phase 3 starts? ★ Yes.
3. P3-D2: accept Option A (Phase 4 posts financial effects only; no pilot before Phase 5)? ★ A.
4. Provider list `evc_plus, zaad, sahal, edahab, premier_wallet, other`; all five wallets seeded, USD-restricted by default? ★ Yes.
5. Seed zero tax rates (owner enters real rates per company)? ★ Yes — rates are an owner decision.
6. CoA template contents (§ 5) and `accounts.system_key`: approve? Who reviews the Somali account names? ★ Template as written; Somali names marked needs-review until the owner (or a reviewer) approves.
7. Account names seeded in the tenant's default language only (bilingual template lives in code)? ★ Yes.
8. Default UoM seed list — add Somali-market units (e.g. *jawaan*/sack, as count labels)? ★ The eight listed.
9. Exchange rates: canonical USD → SOS direction, PATCH corrections allowed (audited), one rate per day? ★ Yes.
10. Company-restricted roles may edit tenant-wide master data (documented limitation)? ★ Yes.
