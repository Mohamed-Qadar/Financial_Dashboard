# Product Requirements — Somali ERP

Status: Draft v0.1 (Phase 0). Items marked **[DECISION]** are open; see the list at the end.

## 1. Problem

Small and medium-sized businesses in Somalia (retail shops, wholesalers, importers,
distributors, service companies) mostly run on paper ledgers, spreadsheets, or generic
POS tools. Existing ERPs (Odoo, ERPNext, SAP Business One) are either expensive, hard to
configure, or do not fit local practice:

- Business is conducted in **USD and Somali shilling (SOS)** at the same time, often in one transaction.
- **Mobile money** (EVC Plus, ZAAD, Sahal, e-Dahab, Premier Wallet) is a primary payment channel, not an afterthought.
- Credit sales to known customers (*deyn*) are common, so receivables tracking matters.
- Staff need a **Somali-language** interface; owners and accountants often prefer English.
- Connectivity and power can be unreliable.

## 2. Target users

| Persona | Needs |
|---|---|
| Owner / manager | Daily sales, cash position, who owes money, stock value, profit per branch |
| Accountant | Chart of accounts, journals, trial balance, P&L, balance sheet, period close |
| Sales / cashier | Fast invoicing, record cash or mobile money payment, print/share receipt |
| Storekeeper | Receive goods, transfer between warehouses, count stock |
| Purchaser | Supplier orders, receipts, supplier bills and payments |
| Tenant administrator | Users, roles, companies, branches, settings |

## 3. Scope

### MVP (Phases 1–9) — the first commercially useful release
Phase order (re-ordered 2026-10-25, see [roadmap](DEVELOPMENT_ROADMAP.md)): master data → sales
→ inventory → purchasing → accounting close → dashboards → hardening and pilot preparation.
1. Multi-tenant accounts. Each tenant can own several companies, each with branches and warehouses.
2. Users, roles and permissions, enforced on the server.
3. Customers and suppliers (contacts).
4. Products, categories, units of measure.
5. Inventory: receipts, deliveries, transfers, returns and adjustments as auditable movements. Stock on hand per warehouse.
6. Sales: quotations/orders, customer invoices, credit notes.
7. Purchasing: purchase orders, goods receipts, supplier bills, debit notes.
8. Payments: cash, bank, and **mobile money recording** (manual entry of the provider transaction reference, with duplicate detection). No live provider API integration in the MVP.
9. Double-entry accounting: chart of accounts, journals, automatic postings from documents, manual journal entries, reversal entries, fiscal periods.
10. Reports: trial balance, P&L, balance sheet, AR/AP aging, customer/supplier statements, stock on hand and stock valuation, sales by product/customer/branch.
11. Multi-currency: USD and SOS from day one, with exchange rates per company.
12. Somali and English user interface.
13. Audit trail for every create, update, post, cancel, and reversal.
14. CSV import/export for master data, plus a backup/restore procedure.

### Later (Phase 10+)
POS with offline tolerance, CRM pipeline, HR/payroll/leave, manufacturing, projects,
subscriptions/billing for the SaaS itself, public API and webhooks, provider integrations
(mobile money, SMS, WhatsApp), mobile apps.

### Explicit non-goals for the MVP
- Microservices, event sourcing, or a plugin marketplace.
- Live payment provider integrations without a verified provider agreement and sandbox.
- Country-specific e-invoicing or tax filing (no national system to target yet).

## 4. Functional requirements (MVP)

**FR-1 Tenancy.** A tenant (business account) is created at sign-up by its first user, who becomes the owner. All business data belongs to exactly one tenant. A user may belong to several tenants and switches between them explicitly.

**FR-2 Organization.** A tenant has 1..n companies (legal entities with their own chart of accounts, base currency, fiscal year and document numbering). A company has 1..n branches and 1..n warehouses.

**FR-3 Access control.** Roles are named sets of permission codes (e.g. `sales.invoice.post`). Roles are assigned per membership and can be limited to specific companies. Every API endpoint checks permissions on the server.

**FR-4 Documents lifecycle.** Business documents follow `draft → posted → (cancelled | reversed)`. Drafts are editable and deletable. Posted documents are immutable. Corrections happen through credit notes, reversal entries, or cancellation that creates compensating records.

**FR-5 Numbering.** Posted documents receive a unique, sequential number per company, document type and fiscal year (e.g. `INV-2026-00042`). Drafts have no number.

**FR-6 Inventory.** Stock quantities change only by posting stock movements. Negative stock is blocked by default **[DECISION: allow per company?]**. Valuation uses weighted average cost **[DECISION]**.

**FR-7 Accounting.** Posting an invoice, bill, payment, or stock movement creates a balanced journal entry in the same database transaction. Manual entries must balance before posting. Closed periods reject postings.

**FR-8 Currency.** Each company has a base currency (default USD **[DECISION]**). Documents may be in any enabled currency with an exchange rate captured at posting time. Reports are in base currency; customer statements can be shown in transaction currency.

**FR-9 Payments.** A payment records method (cash, bank, mobile money, cheque), journal (which cash box, bank account or mobile wallet), amount, currency, and an optional external reference. A mobile money reference cannot be recorded twice in the same wallet journal. Payments are allocated to one or more invoices; partial and over-payments are supported (over-payment becomes customer credit).

**FR-10 Reporting.** Reports are computed from posted ledger data only, filterable by company, branch, date range and currency, and exportable to CSV/PDF.

**FR-11 Localization.** UI strings in Somali and English. Dates displayed in `Africa/Mogadishu` (UTC+3) by default and stored in UTC. Amounts formatted per currency.

**FR-12 Audit.** Every state-changing action records who, when, what, from where (IP, request id), and the field-level change set. Audit logs cannot be edited through the application.

## 5. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | No cross-tenant data access; server-side authorization; OWASP ASVS level 2 as a reference |
| Integrity | Decimal arithmetic for money; atomic business operations; DB constraints back up app validation |
| Performance | Typical list/detail API p95 < 300 ms at 100k invoices per tenant on modest hardware |
| Availability | Daily automated backups with tested restore; RPO ≤ 24 h for MVP |
| Connectivity | UI tolerant of slow networks (small payloads, pagination); offline mode only for POS later |
| Maintainability | Modular monolith, documented decisions, automated tests and CI on every change |
| Observability | Structured logs with request id; health and readiness endpoints |

## 6. Success criteria for the MVP pilot
- One real business runs sales, purchases, stock and payments for 30 days.
- Trial balance balances every day; stock on hand matches a physical count within agreed tolerance.
- Owner can answer "who owes me money" and "what did I earn this month" without a spreadsheet.

## 7. Open business decisions
See [DEVELOPMENT_ROADMAP.md § Open decisions](DEVELOPMENT_ROADMAP.md#open-decisions).
