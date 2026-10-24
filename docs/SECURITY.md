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
- Two database roles (implemented in milestone 2.0):
  - Owner (`POSTGRES_USER`, `somali_erp` locally) — owns tables, runs migrations and
    management commands (`DJANGO_DB_ROLE=owner`). Never used by the web process. In local
    Docker it is a superuser (image default); in production it must not be.
  - Runtime (`POSTGRES_APP_USER`, default `somali_erp_app`) — used by Django by default
    (`DJANGO_DB_ROLE` defaults to `app`). `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
    NOREPLICATION`, owns nothing, DML only, `django_migrations` read-only; later
    `audit_logs`: `INSERT, SELECT` only.
  - `manage.py ensure_db_roles` (run as owner, idempotent) creates/updates the runtime role,
    sets its password from the environment and re-asserts the restricted attributes.
    Migration `core.0001_app_role_grants` grants privileges and sets default privileges so
    tables created by later migrations are covered automatically.
  - Tests connect as the owner; `apps.core.testing.as_app_role()` switches to the runtime role
    for data-access tests. PostgreSQL checks `SET ROLE` against the *session* user, so
    privilege-escalation tests log in as the runtime role for real. For the same reason the
    web process must always **connect** as the runtime role; switching roles on an owner
    connection is not a security boundary.
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
  event (type, outcome, request ID — no metadata, no personal data) is then written to the
  application log at **CRITICAL** level by logger `apps.audit` and the client's response is
  unchanged. Operations must alert on these log lines; they are the only record of the event.

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
- Row-level security on `audit_logs` is added in 2.3, together with tenants (the plan listed
  it under 2.1; it needs the tenant context to be testable).
- Alerts on repeated login failures, 5xx spikes and backup failures (Phase 6).

## 9. Supply chain
- Dependencies pinned (`requirements/*.txt`, `package-lock.json`).
- `pip-audit` and `npm audit` in CI (Phase 6, informational earlier).
- Only well-maintained packages; each new dependency is justified in the PR/commit.

## 10. Backups and recovery (Phase 6)
- Daily `pg_dump` (plus WAL archiving when hosting allows), encrypted, stored off-site, 30-day retention.
- Restore drill documented and performed before the pilot.

## 11. Reporting a vulnerability
Until a public channel exists, report privately to the project owner. Do not open public issues for security bugs.
