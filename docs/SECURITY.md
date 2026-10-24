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

### Layer 1 — Request tenant resolution (implemented in milestone 2.3a)
Tenant → companies → branches (decision D1). The client names the **active company** in the
`X-Company-ID` header on every request; the server derives the tenant from it.
- The header is a *selector*, not a credential. Every request to a company-scoped view
  (`apps.organizations.access.CompanyScopedAPIView`) checks, after authentication: active
  user, **active membership** in the company's tenant, tenant `active`, company `is_active`.
  Nothing about the choice is stored in the session, so stale session state cannot grant
  access; a disabled membership or suspended tenant takes effect on the next request.
  A frontend cookie that remembers the choice (2.8) is only a convenience.
- Missing header, or anything but one canonical UUID → 400 `company_required` (value not
  echoed). Unknown company, another tenant's company, inactive company, disabled membership
  and suspended tenant all answer the **same 404** `not_found`, so existence is not revealed.
- The company is never taken from the body or query string; such fields are ignored.
- Denied attempts are audited (`tenancy.company_access_denied`, no tenant, target = the
  requested id) and limited to 30 per minute per user (then 429 `throttled`, audited once per
  window). Only denials count, keyed by the user: probing slows down only the prober.
- `POST /api/v1/company/select/` records a company switch (`tenancy.company_selected`). It is
  not needed for access: each request is authorized on its own.
- In 2.3 an active membership grants every active company of its tenant; roles (2.4) narrow
  this. Platform staff access to tenant data (support) will require an explicit, audited
  "support session"; it is not a side effect of `is_staff`.
- A test enumerates every URL and fails if a project view is neither company-scoped nor on an
  explicit list of views that work without a company (`tests/test_conventions.py`).

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
- Two database roles (implemented in milestone 2.0):
  - Owner (`POSTGRES_USER`, `somali_erp` locally) — owns tables, runs migrations and
    management commands (`DJANGO_DB_ROLE=owner`). Never used by the web process. In local
    Docker it is a superuser (image default); in production it must not be.
  - Runtime (`POSTGRES_APP_USER`, default `somali_erp_app`) — used by Django by default
    (`DJANGO_DB_ROLE` defaults to `app`). `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
    NOREPLICATION`, owns nothing, DML only, `django_migrations` read-only, `audit_logs`
    `INSERT, SELECT` only, `currencies` `SELECT` only, no `DELETE` on `tenants`,
    `memberships`, `companies`, `branches` (archived, never deleted).
  - `manage.py ensure_db_roles` (run as owner, idempotent) creates/updates the runtime role,
    sets its password from the environment and re-asserts the restricted attributes.
    Migration `core.0001_app_role_grants` grants privileges and sets default privileges so
    tables created by later migrations are covered automatically.
  - Tests connect as the owner; `apps.core.testing.as_app_role()` switches to the runtime role
    for data-access tests. PostgreSQL checks `SET ROLE` against the *session* user, so
    privilege-escalation tests log in as the runtime role for real. For the same reason the
    web process must always **connect** as the runtime role; switching roles on an owner
    connection is not a security boundary.
- Every tenant-owned table (`TenantOwnedModel`) and `tenants`: `ENABLE` and `FORCE ROW LEVEL
  SECURITY` with the policy below (migration helpers in `apps/core/rls.py`):

```sql
-- core.0003: '' (a setting after its transaction ended) and unset both become NULL
CREATE FUNCTION app_current_tenant_id() RETURNS uuid LANGUAGE sql STABLE
  AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$;

CREATE POLICY tenant_isolation ON companies
  USING      (companies.tenant_id = app_current_tenant_id())
  WITH CHECK (companies.tenant_id = app_current_tenant_id());
```

- **Two stages, never combined** (`apps/core/tenancy.py`), both transaction-local
  (`set_config(..., true)`):
  - *User stage* (`app.user_id` only) — resolving the active company and listing companies.
    Extra `SELECT`-only policies show the user's own **active** memberships and the
    tenants/companies those memberships belong to; no branches, no audit rows, no writes.
  - *Tenant stage* (`app.tenant_id` only) — the request's work: every row of that tenant.
  Policy subqueries qualify columns with the table name; an unqualified `tenant_id` inside
  `EXISTS (SELECT … FROM memberships m …)` would bind to `m.tenant_id` and match every tenant
  (caught during development; tests cover both directions).
- **No `SECURITY DEFINER` functions.** Nothing runs with the owner's rights to look across
  tenants (a catalog test enforces it). With `FORCE ROW LEVEL SECURITY`, a non-superuser
  owner is itself subject to RLS, so a definer function would see nothing in production while
  appearing to work locally, where the owner is a superuser.
- **Transactions.** Company-scoped views run in one outermost transaction
  (`atomic(durable=True)`); `ATOMIC_REQUESTS` is off. Error responses (≥ 400) roll it back;
  successful ones clear the context before committing. The context helpers refuse to run
  outside a transaction and use their own savepoint, because a transaction-local setting
  survives `RELEASE SAVEPOINT` (measured) but is undone by `ROLLBACK TO`.
- **Connection reuse and pooling.** Persistent connections (`CONN_MAX_AGE`) are safe: the
  settings end with each transaction (tested on one connection across tenants). Session-level
  `SET` is forbidden (a convention test scans the code). A future pooler must run in
  *transaction* or *session* mode — never *statement* mode — and transaction mode also needs
  `DISABLE_SERVER_SIDE_CURSORS = True`.
- If no setting is present, every tenant table returns zero rows: the system **fails closed**.
- Global tables with no tenant data and no RLS: `users`, `django_session` (needed before a
  tenant is known; users are only listed through memberships), `currencies` (read-only for
  the runtime role), `rate_limit_counters` (HMAC keys only).
- Background jobs and management commands must set the tenant explicitly per unit of work
  (`tenancy.tenant_context()`).
- **Not a boundary against arbitrary SQL.** The runtime role can set `app.tenant_id` itself.
  RLS protects against *application bugs* (a missing filter, a wrong id), not against an
  attacker who can already run SQL as the runtime role; that is prevented by parameterized
  queries (ORM) and the other layers. A test documents this limitation explicitly.

### Layer 4 — Referential integrity
Composite foreign keys `(tenant_id, x_id) → parent(tenant_id, id)` make it impossible to store
a row that references another tenant's data, even through raw SQL. (PostgreSQL FK checks run
without RLS, so this closes the gap RLS leaves.)

### Isolation tests (mandatory from Phase 2)
1. API: tenant A user cannot list, read, update, delete, or act on tenant B objects (404).
2. API: tenant A user cannot reference tenant B IDs in request payloads (400).
3. API: `X-Company-ID` of a company without access → 404, identical to an unknown id.
4. DB (real `somali_erp_app` login): with `app.tenant_id = A`, `SELECT` on each tenant table
   returns no B rows; `INSERT … RETURNING` works for A rows and fails for B rows, in the user
   stage and without context; rows cannot be moved to B.
5. DB: without context, tenant tables return zero rows.
6. Catalog: every `TenantOwnedModel` table (and `tenants`, `audit_logs`, any table with a
   `tenant_id` column) enables and forces RLS; every reference between tenant-owned tables
   has a composite foreign key; no `SECURITY DEFINER` function exists.
7. Privilege matrix: every table's runtime-role privileges are declared and checked exactly
   (`apps/core/tests/test_privilege_matrix.py`).

## 3. Authentication (implemented in milestone 2.2)

### 3.1 Endpoints (`/api/v1/auth/`)
| Endpoint | Access | Behaviour |
|---|---|---|
| `GET csrf/` | anyone | Sets the `csrftoken` cookie (readable by JS, `SameSite=Lax`); 204 |
| `POST login/` | anyone, CSRF | Email + password → session; 200 with the user; 400 `invalid_credentials` |
| `POST logout/` | anyone, CSRF | Ends the session; always 204 |
| `GET me/` | session | Current user |
| `POST password/change/` | session, CSRF | Current + new password; 204 |
| `POST password/reset/` | anyone, CSRF | Always 202 (unless rate-limited) |
| `POST password/reset/confirm/` | anyone, CSRF | uid + token + new password; 204; 400 `invalid_reset_link` |

### 3.2 Controls
- **Sessions:** Django database sessions; cookie `HttpOnly`, `SameSite=Lax`, `Secure` in
  production. Idle timeout 12 h, refreshed on every request (`SESSION_SAVE_EVERY_REQUEST`).
  Absolute limit 7 days after login (`AbsoluteSessionLifetimeMiddleware`; sessions without a
  login time count as expired). The session key is rotated at login (session fixation).
- **CSRF:** every unsafe request needs the `X-CSRFToken` header matching the cookie, and a
  matching `Origin` when the browser sends one. Login, logout and password-reset views use
  `csrf_protect` explicitly, because DRF only checks CSRF for authenticated sessions (login
  CSRF). Failures answer 403 `csrf_failed` in the standard error format.
- **Passwords:** Argon2id (Django's `Argon2PasswordHasher`) first; PBKDF2/scrypt hashes still
  verify and are upgraded at the next login. Validators: similarity, minimum length 10, common
  passwords, all-numeric. Passwords longer than 1024 characters are rejected before hashing.
- **No account enumeration:** unknown email, wrong password and inactive account give the
  same 400 body; Django hashes a dummy password for unknown users so timings are similar.
  Password reset always answers 202. *Limitation:* for an existing account the reset request
  also writes an audit entry and sends e-mail synchronously, so it is measurably slower; a
  background e-mail queue (later) removes this timing difference.
- **Password change:** requires the current password. The current session continues under a
  new session key; every other session of the user is rejected on its next request (the
  session's password hash no longer matches).
- **Password reset:** Django's signed tokens, valid for **1 hour**, single use (the token is
  bound to the password hash and last login, so it dies once used). Links point to
  `DJANGO_FRONTEND_BASE_URL/reset-password?uid=…&token=…`. A reset also ends every session.
  Development prints e-mails to the console; production refuses console/file/memory backends.
- **Rate limits** (atomic PostgreSQL counters, `apps/core/rate_limit.py`; 429 `throttled` with
  `Retry-After`):

  | Action | Limits |
  |---|---|
  | Login | 30/min per IP; 5/min and 20/h per account **and** IP; 100/h per account |
  | Password change | 5/min and 20/h per user |
  | Password reset request | 5/h per IP; 3/h per e-mail |
  | Password reset confirm | 20/h per IP |

  Lockout resistance: per-account limits are keyed by account *and* IP, so failures from one
  address do not block the owner elsewhere; checks stop at the first exceeded limit, so attempts
  already rejected per IP never reach the account-wide cap. There is no hard account lockout.
  *Residual risk:* an attacker with at least five addresses can exhaust the account-wide cap
  (100/h) and block the account for the rest of the hour; a CAPTCHA or e-mail unlock can be
  added if this is seen in practice. Fixed windows allow up to twice a limit around a window
  boundary. Counters store HMAC keys, not e-mail or IP addresses. Throttling is audited once
  per window, so throttled floods do not flood the audit log.
- **Planned:** optional TOTP 2FA for owners/accountants (Phase 6); scoped, hashed, revocable,
  tenant-bound API tokens for integrations (Phase 7).

### 3.3 Client IP addresses
`apps/core/client_ip.py` returns `REMOTE_ADDR` unless the sender is listed in
`DJANGO_TRUSTED_PROXIES` (CIDR list, empty = trust none); then `X-Forwarded-For` is read from
the right and the first untrusted address is the client. Malformed or oversized headers fall
back to `REMOTE_ADDR`.

**Measured Next.js behaviour (2026-10-24, Next.js 16.4.2 rewrites):** the proxy does **not**
add the client address to `X-Forwarded-For`, and it forwards client-supplied
`X-Forwarded-For` and `X-Real-IP` headers unchanged. Trusting the Next.js container would let
every client choose its IP, so **no proxy is trusted** in development. Consequence: requests
through Next.js all appear to come from the Next.js container, so the per-IP login limit is
shared by everyone using the web app in development.

Production requirement before enabling trust: an edge reverse proxy that appends the real
client address to `X-Forwarded-For`; Next.js and Django reachable only through it; then list
the edge proxy and the Next.js network in `DJANGO_TRUSTED_PROXIES`. Production startup fails
unless `DJANGO_TRUSTED_PROXIES` is set explicitly (an empty value is allowed and means "trust
none").

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
- Content Security Policy on the Next.js app (milestone 2.8a, `frontend/src/proxy.ts`): a
  fresh nonce per request; production `script-src 'self' 'nonce-…' 'strict-dynamic'`,
  `style-src 'self' 'nonce-…'`, `connect-src 'self'`, `object-src 'none'`,
  `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`,
  `upgrade-insecure-requests` (verified: every script tag carries the nonce; no violations
  in the browser). Development adds only `'unsafe-eval'`, inline styles and the hot-reload
  websocket. Pages also send `X-Frame-Options: DENY`, `nosniff`, `Permissions-Policy` and
  `Referrer-Policy: no-referrer` (the reset link carries a token).
- Frontend rules (convention tests): no `dangerouslySetInnerHTML`, no inline styles, API calls
  only through the client, browser storage only for UI preferences, preview data and
  API-less providers only in the development gallery. Post-login redirects accept only
  same-site paths (`lib/redirects.ts`, incl. encoded `//` and backslash tricks). The
  password-reset token is removed from the address bar as soon as it is read and is never
  shown or logged.
- The proxy's login redirect only checks that a session cookie exists; the API remains the
  authority (403 → login page, 404 for a company → company picker).
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

### 8.1 Request IDs (milestone 2.1)
- Every HTTP request gets an ID (`RequestIDMiddleware`, first middleware). It is returned in
  the `X-Request-ID` response header, in every error body (`error.request_id`), in every log
  line, and in audit entries.
- **Validation policy for a client-supplied `X-Request-ID`:** accepted only as a canonical
  hyphenated UUID (36 characters, hex digits and hyphens), normalized to lower case. Missing,
  empty, longer, differently formatted values or values with control characters are ignored
  and replaced by a new random UUID4. The value is never parsed further.
- Request IDs are for correlation only. Clients can pick any valid UUID (including one used
  before), so an ID is never used for authorization, rate limiting or deduplication.

### 8.2 Application logs
- JSON lines by default (`DJANGO_LOG_FORMAT=json`; `text` for local reading). JSON encoding
  escapes newlines and control characters, so user-controlled text cannot forge log lines.
- One access line per request: method, path **without query string**, status, duration,
  request ID. No headers, bodies, cookies or query parameters are logged.
- Never log passwords, tokens, session IDs, full card or wallet numbers.

### 8.3 Audit log (milestone 2.1)
Table `audit_logs`, written only through `apps.audit.services.record_event()`.

| Field | Content |
|---|---|
| `occurred_at` | Database clock (`now()`), not the application clock |
| `event_type` | From the catalog in `apps/audit/events.py`; unknown types are rejected |
| `outcome` | `success`, `failure` or `denied` |
| `actor_type`, `actor_id` | `user` + user id, `system`, or `anonymous` (DB constraint keeps them consistent) |
| `tenant_id`, `company_id` | When known. Plain UUIDs, no foreign keys, so audit rows never cascade from deletions |
| `target_type`, `target_id` | What the event is about (≤ 64 characters) |
| `request_id`, `ip_address` | Correlation; `ip_address` is `REMOTE_ADDR` (see limitations) |
| `metadata` | Small JSON object (≤ 4 KB). Keys containing password, secret, token, session, cookie, authorization, csrf, api_key, private_key or otp are stored as `[redacted]`; strings are cut at 500 characters |

Not stored on purpose: e-mail addresses, names, user agents, request bodies.

**Row-level security (milestone 2.3a, migration `audit.0002`).** Roles subject to RLS read
only entries of the tenant stage's tenant; **platform entries (`tenant_id` NULL: logins,
role maintenance, denied company access) are not readable by the runtime role in any stage**.
They may be appended only outside a tenant context; tenant entries only for the current
tenant. PostgreSQL applies read policies to rows returned by `INSERT … RETURNING`, so
`record_event()` takes the id from the sequence (`nextval`) and the time from
`statement_timestamp()` and inserts without `RETURNING`. Inside a tenant request, tenant and
company default to the request's active company. Today no application code reads audit
entries; the owner reads them for support and tests.

**Transaction rule.** `record_event()` writes on the caller's connection, so an entry commits
or rolls back together with the operation it describes. A `success` event outside
`transaction.atomic()` raises an error, so a success can never be recorded for work that later
rolls back. `failure`/`denied` events may be written after the failed work rolled back.
Failure events are written with `record_failure_event()` after the failed work has rolled
back, in their own outermost transaction (`atomic(durable=True)`; calling it inside an open
transaction raises). Authentication views manage their transactions explicitly; when
`ATOMIC_REQUESTS` is enabled in 2.3 they are marked non-atomic.

**If audit storage fails** (milestone 2.2):
- *Success events* are fail-closed: the operation and its event share a transaction, so a
  failed audit write rolls the operation back and the client gets 503 `service_unavailable`.
  Login additionally discards the session, so no unaudited authenticated session can exist;
  a password-reset e-mail is only sent after its request was audited (the response stays
  202 so a storage failure does not reveal which addresses have accounts).
- *Failure/denied events* cannot be stored when the audit table itself is unavailable; the
  event (type, outcome, request ID, error class and SQLSTATE — no metadata, no personal data,
  **no database error text**, because PostgreSQL messages can quote the rejected row,
  including its IP address and metadata; measured) is then written to the application log at
  **CRITICAL** level by logger `apps.audit` and the client's response is unchanged.
  Operations must alert on these log lines; they are the only record of the event.
- A failure event of a tenant (e.g. a company selection whose audit write failed) is written
  after the rollback in that tenant's context, so it keeps its tenant id.

**Immutability controls.**
1. ORM: `AuditLog.save()` on an existing row, `delete()`, `QuerySet.update/delete/bulk_update` raise.
2. Privileges: the runtime role `somali_erp_app` has only `SELECT, INSERT` on `audit_logs`
   (no `UPDATE`, `DELETE`, `TRUNCATE`, `TRIGGER`, `REFERENCES`), cannot `setval` its sequence,
   and as a non-owner cannot alter, disable or drop the trigger or the table.
3. Trigger `audit_logs_append_only` rejects `UPDATE` and `DELETE` for **every** role,
   including the owner, unless someone deliberately removes it.
4. The table, trigger and privilege restriction are created in one migration, so the table
   never exists unprotected.

All of this is tested, including with a real login as `somali_erp_app`.

**Limitations — what can still change audit data.**
- The **owner role** (`somali_erp`) owns the table: it can `TRUNCATE` it, disable or drop
  the trigger, then update or delete rows, or drop the table. The trigger only stops
  accidental changes; it does not stop a deliberate owner.
- A **superuser** (the owner is one in local Docker) can additionally bypass triggers
  (`session_replication_role = replica`), edit files on disk, or restore an older backup.
- Anyone with access to **database backups** can alter a backup and restore it.
- The audit log is therefore tamper-*resistant* against the application and its runtime role,
  but not tamper-*proof* against database administrators.
- Reversing migration `audit.0001` drops the table (development only; backups first).

**Future work for independently controlled audit storage** (before production / pilot):
- Production owner role that is not a superuser, with credentials held separately from the
  application's deployment secrets.
- Ship audit entries continuously to storage the database administrators cannot modify:
  an append-only/WORM object store (e.g. object lock), a separate logging service, or a
  separate database with different administrators.
- Optional tamper evidence: hash-chain entries (each row stores a hash of the previous row) and
  periodically sign or externally store the latest hash, so edits become detectable.
- Retention and access policy for audit data (who may read it, how long it is kept).

### 8.4 Known gaps (to be closed in later milestones)
- Client IPs behind the Next.js proxy are the proxy's address until an edge proxy is deployed
  (see § 3.3).
- Alerts on repeated login failures, 5xx spikes and backup failures (Phase 6).

**Must be closed before a pilot or production use:**
1. Edge reverse proxy that appends the real client address; `DJANGO_TRUSTED_PROXIES` set
   (otherwise per-IP limits are shared by all users).
2. Alerting on `apps.audit` CRITICAL log lines (the only record of unstorable failure events).
3. Real e-mail provider with a background queue (removes the password-reset timing difference).
4. Decision on account-level lockout abuse (CAPTCHA or e-mail unlock) if the residual risk in
   § 3.2 is seen in practice.
5. Production owner role that is not a superuser; web process connects as the runtime role.

## 9. Supply chain
- Dependencies pinned (`requirements/*.txt`, `package-lock.json`).
- `pip-audit` and `npm audit` in CI (Phase 6, informational earlier).
- Only well-maintained packages; each new dependency is justified in the PR/commit.

## 10. Backups and recovery (Phase 6)
- Daily `pg_dump` (plus WAL archiving when hosting allows), encrypted, stored off-site, 30-day retention.
- Restore drill documented and performed before the pilot.

## 11. Reporting a vulnerability
Until a public channel exists, report privately to the project owner. Do not open public issues for security bugs.
