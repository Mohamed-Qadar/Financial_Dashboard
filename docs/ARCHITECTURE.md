# Architecture — Somali ERP

Status: Draft v0.1 (Phase 0). Decisions are recorded inline as **ADR-n** so the reasoning stays next to the design.

## 1. Overview

```
Browser
  │  HTTPS, same origin (cookies)
  ▼
Next.js (frontend/)  ── renders UI, proxies /api/* to Django
  │  HTTP (internal network)
  ▼
Django + DRF (backend/)  ── authentication, authorization, business rules, posting
  │
  ├── PostgreSQL  ── business data, ledgers, audit log (RLS as defense in depth)
  └── File storage ── attachments (local volume in dev, S3-compatible later)
```

**ADR-1 Modular monolith.** One Django project, one database, one deployable backend.
For a solo developer this keeps transactions simple (a sale that touches stock, invoice and
ledger is a single DB transaction), keeps deployment cheap, and avoids distributed-system
failure modes. Modules have explicit boundaries so that extraction stays possible later.

**ADR-2 Django REST Framework + PostgreSQL.** Mature, well-documented, strong ORM and
migrations, good admin for internal support, and PostgreSQL gives `NUMERIC`, row-level
security, constraints, and transactional DDL.

**ADR-3 Next.js as a separate frontend.** Rich data-entry UI (grids, forms, dashboards)
in TypeScript. The browser talks only to the Next.js origin; Next.js forwards `/api/*` to
Django. This lets us use secure HttpOnly session cookies without cross-site cookie
configuration. Next.js holds **no** business rules and is never a security boundary.

## 2. Backend modules

```
backend/
├── config/            # settings, root URLs, WSGI/ASGI
├── apps/
│   ├── core/          # shared base models, health checks, errors, money/decimal utils
│   ├── accounts/      # users, authentication, roles, permissions, memberships
│   ├── tenants/       # tenant accounts, tenant context, subscriptions (later)
│   ├── organizations/ # companies, branches, warehouses, fiscal settings
│   ├── contacts/      # customers and suppliers
│   ├── catalog/       # products, categories, units of measure, taxes
│   ├── inventory/     # stock movements, stock ledger, balances, valuation
│   ├── sales/         # quotations/orders, customer invoices, credit notes
│   ├── purchasing/    # purchase orders, receipts, supplier bills
│   ├── finance/       # accounts, journals, entries, payments, currencies, periods
│   ├── reporting/     # read-only report queries
│   └── audit/         # audit log
└── tests/             # cross-module and integration tests
```

`core` was added to the original module list: health checks, the error format, and
shared model mixins need a home that every other module can depend on.

Apps are created only when the phase that needs them starts; no empty placeholder apps.

### Dependency direction

```
reporting ─► sales, purchasing, inventory, finance (read-only)
sales, purchasing ─► inventory, finance, catalog, contacts
inventory, finance ─► catalog, organizations
everything ─► tenants, accounts, audit, core
```

Lower modules never import higher ones. When `finance` must react to a sale, `sales` calls
a `finance` service function (`finance.services.post_journal_entry(...)`); `finance` does not
know about invoices.

### Layering inside each app

| Layer | File(s) | Responsibility |
|---|---|---|
| Models | `models.py` | Schema, constraints, simple invariants. No business workflows. |
| Selectors | `selectors.py` | Tenant-scoped read queries |
| Services | `services.py` | Business operations (`post_invoice`, `record_payment`), each wrapped in `transaction.atomic()` |
| API | `serializers.py`, `views.py`, `urls.py` | Input validation, permission checks, HTTP mapping |
| Tests | `tests/` | Unit tests for services, API tests incl. isolation and permission tests |

**ADR-4 Service layer for writes.** Posting logic lives in plain functions, not in model
`save()` or serializers. Views call services; services are tested directly. This keeps
multi-table operations explicit and atomic.

**ADR-5 Custom user model from the first migration.** `apps.accounts.User` (UUID id,
case-insensitive unique email, no username) was created in Phase 1 even though login arrives
in Phase 2, because Django cannot cleanly swap `AUTH_USER_MODEL` after the first migration.

## 3. Cross-cutting design

### 3.1 Tenant context (milestone 2.3a)
1. Request is authenticated (session).
2. Company-scoped views inherit `apps.organizations.access.CompanyScopedAPIView`, which opens
   the view's outermost transaction (`ATOMIC_REQUESTS` stays off).
3. The active company comes from the `X-Company-ID` header and is **verified on every
   request** against the user's active membership and the tenant/company status (user stage:
   `app.user_id`). Failure → the same 404 for every case.
4. The tenant stage sets `app.tenant_id` (transaction-local) and the view gets
   `request.tenant`, `request.company`, `request.membership`.
5. All querysets go through selectors that take them explicitly; RLS policies reject anything
   that slips through. Error responses roll back; failure audit events are written afterwards.

Full details in [SECURITY.md](SECURITY.md).

### 3.2 Transactions
- Every write endpoint runs in a transaction (service functions use `transaction.atomic()`).
- Rows that serialize concurrent work are locked with `SELECT ... FOR UPDATE`:
  document sequences, stock balances, invoices being paid.
- Side effects outside the DB (emails, SMS, webhooks) are sent with
  `transaction.on_commit()` so they never fire for rolled-back work.

### 3.3 Money and quantities
- Python `decimal.Decimal` everywhere; DB columns `NUMERIC`. Float is banned for amounts:
  `tests/test_conventions.py` fails if any project model has a `FloatField`; code review covers the rest.
- Amounts: `NUMERIC(18,2)`; unit prices and costs: `NUMERIC(18,4)`; quantities: `NUMERIC(18,4)`;
  exchange rates: `NUMERIC(20,8)`.
- Rounding: `ROUND_HALF_UP` to the currency's minor units, applied at line level, then totals
  are sums of rounded lines (what the customer sees on paper adds up).
- Every amount is paired with a currency code. Ledger lines store both the base-currency
  debit/credit and the transaction-currency amount.

### 3.4 Document lifecycle and numbering
- States: `draft → posted → cancelled/reversed`. Posting is a service call that validates,
  allocates a number, writes stock and ledger effects, and records an audit event atomically.
- Numbers come from `document_sequences` locked `FOR UPDATE` within the posting transaction,
  so a rollback releases the number and numbers stay gap-free under concurrency.

### 3.5 API conventions
- Base path `/api/v1/`. JSON only. OpenAPI schema at `/api/schema/`, Swagger UI at `/api/docs/` (dev).
- Resource IDs are UUIDs.
- Pagination: page-number, default 50, max 200.
- Business actions are explicit endpoints: `POST /api/v1/sales/invoices/{id}/post/`.
- Error format (implemented in Phase 1):

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid input.",
    "details": {"quantity": ["Ensure this value is greater than 0."]},
    "request_id": "3f2b8c1e-4d5a-4b6c-9e7f-0a1b2c3d4e5f"
  }
}
```

- Every response carries `X-Request-ID`; error bodies repeat it as `request_id` (milestone 2.1,
  policy in [SECURITY.md § 8.1](SECURITY.md#81-request-ids-milestone-21)).
- Logs are JSON lines with the request ID; security-relevant events go to the append-only
  audit log via `apps.audit.services.record_event()` ([SECURITY.md § 8.3](SECURITY.md#83-audit-log-milestone-21)).

### 3.6 Time
Stored as UTC (`timestamptz`, `USE_TZ=True`). Business dates (invoice date, posting date) are
`date` columns interpreted in the company's timezone (default `Africa/Mogadishu`).

### 3.7 Localization
Backend: Django i18n for messages and error text (`so`, `en`), milestone 2.7. Frontend (M2.8a):
typed dictionaries `frontend/src/lib/i18n/messages/{en,so}.ts`, Somali by default, the choice
kept in the `erp_lang` cookie (no locale in the URL). Errors are shown by backend error
*code*, so the UI is localized even while backend messages are English. Somali drafts are
marked "needs review" (decision D12). Somali month/country/currency names come from the
frontend's own table: Chrome ships no Somali locale data, so `Intl` would answer in English.

### 3.8 Files
Attachments stored outside the DB (local volume in development, S3-compatible object storage
in production), referenced by a DB row that carries `tenant_id`. Served only through
authorized endpoints or short-lived signed URLs.

## 4. Frontend (milestone 2.8a)

```
frontend/src/
├── proxy.ts            # Next.js 16 proxy (formerly middleware): CSP nonce, login redirect
├── app/
│   ├── (auth)/         # login, forgot-password, reset-password (public)
│   ├── (app)/          # select-company, c/[companyId]/…, account (session required)
│   ├── ui-preview/     # component gallery, development only (404 elsewhere)
│   ├── not-found.tsx, error.tsx
├── components/
│   ├── ui/             # Button, Field, Alert, Card, Menu, States (empty/error/loading), Icon
│   ├── shell/          # AppShell (sidebar, top bar), CompanySwitcher, UserMenu
│   ├── auth/, company/, account/
├── lib/
│   ├── api/            # client (CSRF, X-Company-ID, error envelope), endpoints, types
│   ├── i18n/           # dictionaries, LocaleProvider, server locale
│   ├── session/, company/  # SessionProvider, CompanyProvider
│   ├── redirects.ts, security.ts, format.ts
├── styles/             # tokens.css, base.css, components.css, layout.css
└── dev/                # preview data (development gallery only)
```

- TypeScript strict mode; no runtime dependencies beyond Next.js and React.
- **Active company in the URL**: `/c/<companyId>/…`, one per browser tab. The id is sent as
  `X-Company-ID` and verified by the server on every request; the frontend stores nothing
  that grants access (a per-tab "last company" only feeds a back link).
- Authenticated data is fetched in the browser through `lib/api/client.ts` (same-origin
  `/api/*`, session cookie, `X-CSRFToken` on unsafe requests, `ApiError` by error code).
- Production screens show only data returned by the API; preview data lives in `src/dev`
  and a convention test forbids importing it elsewhere.
- Styling: CSS custom properties (light theme), global stylesheets with `ui-`/`shell-`
  prefixes and data-attribute states; no inline styles (the CSP forbids them).
- Tests with Vitest + Testing Library (`fireEvent`; no user-event yet).

## 5. Environments and tooling

| Concern | Choice |
|---|---|
| Local dev | Docker Compose: `db` (PostgreSQL 17), `backend` (Django dev server), `frontend` (Next.js dev server). In the container the Next.js dev server uses webpack with polling, because file events do not cross the Windows bind mount and Turbopack has no polling fallback. Builds use Turbopack. |
| API proxy | `next.config.ts` rewrites `/api/*` to Django with a separate rule for trailing-slash URLs (otherwise `:path*` drops the slash and Django's `APPEND_SLASH` redirect loops) |
| Backend tests | pytest + pytest-django against real PostgreSQL (no SQLite, so constraints and RLS are tested for real) |
| Lint/format | Ruff (Python), ESLint + `tsc --noEmit` (TypeScript) |
| CI | GitHub Actions workflow (backend lint + tests with a PostgreSQL service; frontend lint, type-check, tests, build). The project is local-only for now, so the same steps are run locally in Docker. |
| Version control | Local Git only; no remote until the owner approves publishing at project completion |
| Production (Phase 6) | Gunicorn behind a reverse proxy with TLS, managed or self-hosted PostgreSQL with backups |

### Pinned versions (Phase 1)

| Component | Version | Reason |
|---|---|---|
| Python | 3.12 (container) | Supported by Django 5.2; local 3.11 also works |
| Django | 5.2.x LTS | Long-term support until April 2028 |
| Django REST Framework | 3.18.x | Supports Django 5.2 |
| psycopg | 3.3.x | Modern PostgreSQL driver |
| drf-spectacular | 0.30.x | OpenAPI schema generation |
| PostgreSQL | 17 | Stable, supported until 2029 |
| Node.js | 22 LTS | Required by Next.js 16 (≥ 20.9) |
| Next.js | 16.4.2 | Current line; includes the October 2026 coordinated React/Next patch releases |
| React | 19.3.1 | Patched release matching Next.js |
| TypeScript | 5.9.x | TypeScript 7 is too new to rely on for tooling compatibility |
| Vitest / Vite | 4.1.x / 7.3.x | Stable majors; Vitest 5 is very recent |
| ESLint | 9.39.x | ESLint 9 is end-of-life, but `eslint-config-next` plugins (react, jsx-a11y, import) do not support ESLint 10 yet |
| npm | 11.6.x | npm 10's `npm install` (bundled with Node 22) crashes resolving the Vitest peer tree; `npm ci` works on both |

## 6. Things deliberately not used (yet)

| Not used | Why | Revisit when |
|---|---|---|
| Celery / Redis | No background jobs needed until reports/imports grow | Large imports, scheduled reports, email/SMS |
| Schema-per-tenant | Migrations and connection handling get complex with many tenants | Never, unless a customer requires physical isolation |
| GraphQL | REST with explicit action endpoints fits document workflows | — |
| JWT in browser storage | Exposed to XSS; session cookies are safer for a first-party UI | Mobile app / third-party API (use tokens there) |
