# Security and Data Isolation — Somali ERP

Status: Draft v0.1 (Phase 0). Reference standard: OWASP ASVS 4/5 level 2.

## 1. Threats we design against

| Threat | Example | Primary control |
|---|---|---|
| Cross-tenant data access | Tenant A user requests `/invoices/<id of tenant B>` | Tenant-scoped queries + permission checks + PostgreSQL RLS + composite FKs |
| Privilege escalation inside a tenant | Cashier posts a journal entry or edits roles | Server-side permission codes on every endpoint and action |
| Tampering with financial history | Editing a posted invoice to hide a sale | Immutable posted records, DB triggers, reversal-only corrections, audit log |
| Account takeover | Password guessing, stolen session | Argon2 hashing, rate limiting, HttpOnly/Secure cookies, session rotation, optional 2FA |
| Injection / XSS / CSRF | Malicious product name rendered in UI | ORM parameterization, React escaping, CSP, Django CSRF |
| Secret leakage | DB password committed to Git | Environment variables, `.env` git-ignored, secret scanning in CI |
| Data loss | Disk failure, bad migration | Automated encrypted backups, tested restore, migrations reviewed |

## 2. Tenant isolation strategy

**Model:** shared database, shared schema, `tenant_id` on every tenant-owned row.
Chosen over schema-per-tenant or database-per-tenant because migrations, connection pooling,
reporting and operations stay simple for a small team. Isolation is enforced in four layers,
so a single bug does not become a data leak:

### Layer 1 — Request tenant resolution
- The active tenant comes from the `X-Tenant-ID` header and is accepted **only if** the
  authenticated user has an `active` membership in it. Otherwise: `403`.
- The tenant is attached to the request object; it is never read from request bodies.
- Platform staff access to tenant data (support) requires an explicit, audited
  "support session"; it is not a side effect of `is_staff`.

### Layer 2 — Application query scoping
- Tenant-owned models inherit `TenantOwnedModel`; their default manager is not used for API
  queries. Views get querysets only from selectors that take the tenant explicitly
  (`selectors.invoices_for(tenant=..., company=...)`).
- Objects from another tenant return **404**, not 403, to avoid confirming existence.
- Foreign keys in input (e.g. `customer_id`) are resolved inside the tenant scope; an ID from
  another tenant is a validation error.
- A test helper asserts, for every API endpoint, that tenant B's objects are invisible and
  immutable to tenant A users (list, retrieve, update, delete, custom actions).

### Layer 3 — PostgreSQL Row-Level Security (defense in depth)
- Two database roles:
  - `erp_owner` — owns tables, runs migrations. Never used by the web process.
  - `erp_app` — used by Django at runtime. `NOSUPERUSER NOBYPASSRLS`, not a table owner,
    only DML grants. `audit_logs`: `INSERT, SELECT` only.
- Every tenant-owned table: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` with

```sql
CREATE POLICY tenant_isolation ON invoices
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

- Django sets the value per request **inside the request transaction**:
  `SELECT set_config('app.tenant_id', %s, true)` (transaction-local, so pooled connections
  cannot carry it into the next request).
- If the setting is missing, `current_setting(..., true)` is NULL and the policy matches no
  rows: the system **fails closed**.
- Cross-tenant tables needed before a tenant is known (`users`, `memberships` lookup at login,
  `permissions`, `currencies`) have dedicated policies or no tenant data.
- Background jobs and management commands must set the tenant explicitly per unit of work.

### Layer 4 — Referential integrity
Composite foreign keys `(tenant_id, x_id) → parent(tenant_id, id)` make it impossible to store
a row that references another tenant's data, even through raw SQL. (PostgreSQL FK checks run
without RLS, so this closes the gap RLS leaves.)

### Isolation tests (mandatory from Phase 2)
1. API: tenant A user cannot list, read, update, delete, or act on tenant B objects (404).
2. API: tenant A user cannot reference tenant B IDs in request payloads (400).
3. API: forged `X-Tenant-ID` for a tenant without membership → 403.
4. DB: as `erp_app` with `app.tenant_id = A`, `SELECT` on each tenant table returns no B rows; `INSERT` with B's id fails.
5. DB: as `erp_app` without `app.tenant_id`, tenant tables return zero rows.
6. A test enumerates all models inheriting `TenantOwnedModel` and fails if any table lacks an RLS policy.

## 3. Authentication

- **Session cookies** (Django sessions) for the first-party web UI: `HttpOnly`, `Secure` (prod),
  `SameSite=Lax`, rotated on login, idle timeout (e.g. 12 h) and absolute timeout.
- Browser calls go to the Next.js origin, which proxies `/api/*` to Django, so cookies are first-party.
- CSRF protection on all unsafe methods (Django CSRF token, sent as header by the API client).
- Passwords: Argon2 hasher, Django password validators, minimum length 10.
- Login and password-reset endpoints rate-limited per IP and per account; generic error
  messages ("invalid credentials") to avoid account enumeration.
- Optional TOTP 2FA for owners/accountants (Phase 6).
- API tokens for integrations (Phase 7) are scoped, hashed at rest, revocable, and tenant-bound.

## 4. Authorization

- Permission codes: `<module>.<resource>.<action>`, e.g. `sales.invoice.view`,
  `sales.invoice.create`, `sales.invoice.post`, `finance.journal_entry.reverse`, `accounts.role.manage`.
- Permissions attach to roles; roles attach to memberships, optionally limited to a company.
- Every view declares its required permission; a test fails if an endpoint has none
  (except explicitly public ones such as health checks and login).
- Sensitive actions (post, cancel, reverse, role change, period close) are separate permissions
  from create/edit, enabling separation of duties.
- DRF default permission is `IsAuthenticated` — new endpoints are closed unless opened deliberately.

## 5. Financial integrity controls
- Posted documents and journal entries are immutable (service checks + DB triggers).
- Corrections via credit notes, reversal entries, compensating stock movements.
- Closed fiscal periods reject postings.
- Every posting writes an audit log row in the same transaction.
- Duplicate protection: unique mobile money reference per wallet journal; unique supplier bill reference per supplier.

## 6. Application security baseline
- Django security middleware; in production `SECURE_SSL_REDIRECT`, HSTS, `SECURE_PROXY_SSL_HEADER`
  (behind a trusted proxy), secure cookies, `X-Frame-Options: DENY`, `Referrer-Policy`.
- Content Security Policy on the Next.js app (Phase 2+).
- `DEBUG=False` and a strong `DJANGO_SECRET_KEY` are required outside development;
  the settings module refuses to start otherwise.
- Strict `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.
- Input validation in serializers; DB constraints as the last line.
- File uploads: size limit, content-type allow-list, stored outside web root with random keys,
  served through authorized endpoints.
- Error responses never include stack traces or SQL in production.
- Health endpoints expose status only, not versions or configuration.

## 7. Secrets and configuration
- All secrets via environment variables. `.env` is git-ignored; `.env.example` documents keys with dummy values.
- No credentials in code, fixtures, tests, or CI logs. CI uses throwaway test credentials only.
- Production secrets in the hosting platform's secret store.

## 8. Logging, audit and monitoring
- Structured application logs with request id, tenant id, user id; no passwords, tokens, or full card/wallet numbers.
- Audit log (business events) separate from technical logs, append-only for the app role.
- Alerts on repeated login failures, 5xx spikes, and backup failures (Phase 6).

## 9. Supply chain
- Dependencies pinned (`requirements/*.txt`, `package-lock.json`).
- `pip-audit` and `npm audit` in CI (Phase 6, informational earlier).
- Only well-maintained packages; each new dependency is justified in the PR/commit.

## 10. Backups and recovery (Phase 6)
- Daily `pg_dump` (plus WAL archiving when hosting allows), encrypted, stored off-site, 30-day retention.
- Restore drill documented and performed before the pilot.

## 11. Reporting a vulnerability
Until a public channel exists, report privately to the project owner. Do not open public issues for security bugs.
