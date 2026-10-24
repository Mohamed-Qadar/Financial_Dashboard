# Phase 2 Implementation Plan — Identity, Tenancy and Access Control

Status: **Approved plan.** All recommended (★) options in section 2 were accepted by the owner
on 2026-10-24. Each milestone is still implemented only after the owner approves it.
Language of the owner's review: Turkish summary in chat; this document is the reference.

## 0. Inputs

Confirmed product decisions (2026-10-24):

| Topic | Decision |
|---|---|
| Target market | Federal Republic of Somalia (currencies USD and SOS; no Somaliland shilling) |
| Default company currency | USD |
| Authentication | Email + password |
| Interface languages | Somali and English |
| Hosting / Git | Local only; no remote, no push, nothing published |
| Project location | Stays in OneDrive for now |
| Data | Existing database data and Docker volumes are preserved; no resets |

## 1. Current state (inspected)

| Item | Finding | Consequence for Phase 2 |
|---|---|---|
| Models | Only `accounts.User` (UUID PK, unique lower-cased email, `preferred_language` en/so, `is_staff`, `PermissionsMixin`) | Reused as is; no change to the user table is required |
| Migrations | `accounts.0001_initial` plus Django contrib migrations (16 applied) | All Phase 2 migrations are additive |
| Data | `users`: 0 rows, `django_session`: 0 rows | No data migration needed; nothing to back-fill |
| DB role used by Django | `somali_erp` is **SUPERUSER and BYPASSRLS** (Docker image default) | **RLS would be silently ignored.** A separate non-superuser runtime role is a hard prerequisite (milestone 2.0) |
| Role creation | Docker init scripts run only on an empty volume | Runtime role must be created by an idempotent management command, not by re-initialising the volume |
| Somali locale | `so` is not in Django's `LANG_INFO`; Django/DRF ship no Somali translations; `msgfmt` (gettext) is not in the backend image | Settings must register `so`; we translate every user-facing message we expose; Dockerfile needs `gettext` |
| Frontend locale | Node ICU formats `so-SO` (e.g. "Sabti, Oktoobar 24, 2026", "US$1,234.50") | Dates/numbers can use `Intl` directly |
| Docs | ARCHITECTURE/SECURITY assume tenant selection via `X-Tenant-ID`; the Phase 2 brief asks for **active-company** selection | Resolved by decision D1 below; docs updated in the milestone that implements it |

## 2. Decisions (resolved)

**All ★ options below were accepted on 2026-10-24** and are now binding for Phase 2. The
alternatives are kept for the record.

**D1 — Isolation boundary: tenant above companies, or company as the tenant?** (blocks 2.3)
- ★ **A. Tenant (business account) → companies → branches** (current docs). Users join a tenant
  (membership); access to individual companies comes from role assignments (all companies or
  specific ones). The client selects an **active company**; the server derives the tenant from
  it. Supports business groups with several legal entities sharing customers/products and
  consolidated reporting later.
- B. **Company = tenant.** One level only. Simpler, but a group with two companies needs two
  separate accounts, re-invited users, duplicated master data, no consolidation.

**D2 — What RLS enforces** (blocks 2.3)
- ★ RLS enforces the **tenant** boundary (the customer-to-customer leak we must never have).
  Company-level restrictions *inside* a tenant are enforced by the application (permissions +
  selectors) and by composite foreign keys, all covered by tests.
- Alternative: RLS also enforces allowed companies per user. Stronger, but policies need a
  per-request list of company ids and become harder to reason about and slower.

**D3 — How people get accounts** (blocks 2.3 and 2.6)
- ★ Self-registration (creates user + tenant + first company) controlled by a setting
  `REGISTRATION_OPEN` (on in development). Additional staff join through **invitation links**
  created by an administrator; the link can be shared by email *or* copied and sent via
  WhatsApp/SMS, so onboarding does not depend on an email provider.
- Alternatives: invite-only (platform operator creates tenants); or admins create users with
  temporary passwords (simpler, but passwords travel through people).

**D4 — Email delivery** (blocks password reset in 2.2, email verification)
- There is no email provider yet. ★ Phase 2 uses Django's console email backend in development;
  password reset and email verification flows are built and tested but only "deliver" to the
  log. A real provider is chosen before the pilot.
- Decide: should email verification be **required** before first login? ★ Not in Phase 2
  (record `email_verified_at`, enforce later when a provider exists).

**D5 — Login throttling storage** (blocks 2.2)
- ★ Django database cache table (`createcachetable`) — no new infrastructure, shared across
  worker processes. Alternative: Redis (new service; better at scale).

**D6 — New dependencies** (blocks 2.2 and 2.7)
- ★ `argon2-cffi` (Argon2 password hashing, recommended by Django and OWASP).
- ★ `gettext` system package in the backend image (compiles Somali/English message catalogs).
- No frontend i18n library (see D8).

**D7 — Default roles and permission granularity** (blocks 2.4)
- ★ Seeded role templates per tenant: **Owner** (everything, cannot be deleted, ≥ 1 per tenant),
  **Administrator** (users, roles, companies, branches; no ownership transfer), **Accountant**,
  **Sales**, **Storekeeper**, **Viewer**. In Phase 2 only the organization/user permissions
  exist; module permissions are added by the phases that create those modules.
- ★ Permission codes `module.resource.action` (e.g. `organizations.branch.create`). Custom
  roles per tenant allowed, but a user can only grant permissions they hold themselves.

**D8 — Frontend localization approach** (blocks 2.8)
- ★ Typed message dictionaries (`so.ts`, `en.ts`) with a small helper, locale from the user's
  `preferred_language` (cookie before login), **no locale in the URL** (internal business app,
  no SEO need). No dependency.
- Alternative: `next-intl` (mature library, ICU message syntax, one more dependency).
- Decide: **default language for new users and the login page** — ★ Somali, with an English switch.

**D9 — Warehouse at registration** (blocks 2.3)
- The current roadmap says registration also creates a default warehouse. Warehouses belong to
  inventory (Phase 3). ★ Move "default warehouse" to Phase 3; Phase 2 creates tenant, owner
  membership, company and a default branch.

**D10 — Where the currency reference table lives** (blocks 2.3)
- `companies.base_currency_code` needs `currencies` (USD, SOS). ★ Create the `finance` app now
  with only the `Currency` reference model (finance owns money concepts later). Alternative:
  a plain `CharField` validated against a list, converted to a FK later (migration risk).

**D11 — Session lifetime** (blocks 2.2)
- ★ 12-hour sliding idle timeout, 7-day absolute maximum, session rotated at login and on
  password change, all other sessions ended on password change.

**D12 — Somali translations** (blocks 2.7/2.8 completeness, not their start)
- Who writes/reviews Somali text? ★ Claude drafts, every Somali string is marked
  "needs review" in the catalog until the owner (or a reviewer) approves it. Messages Django/DRF
  generate internally (e.g. password validator text) are translated only where we expose them.

## 3. Cross-cutting design (applies to all milestones)

### 3.1 Database roles (milestone 2.0)
| Role | Attributes | Used by |
|---|---|---|
| `somali_erp` (existing, owner) | SUPERUSER in local Docker only; in production a non-superuser owner | `migrate`, management commands, tests' database creation |
| `somali_erp_app` (new) | `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`, not a table owner | The running web process |

- Grants: `SELECT, INSERT, UPDATE, DELETE` on application tables, `USAGE` on sequences,
  `ALTER DEFAULT PRIVILEGES FOR ROLE somali_erp` so future tables are covered. No DDL.
  `audit_logs`: `INSERT, SELECT` only. `django_migrations`: `SELECT` only.
- Settings select credentials with `DJANGO_DB_ROLE=app|owner` (default `app`); compose runs
  `migrate` with `owner` and `runserver` with `app`.
- **RLS in API tests:** inside the tenant context the request transaction runs
  `SET LOCAL ROLE somali_erp_app`. In production this is a no-op (already that role); in tests
  (connected as owner) it makes every API test run under RLS. It is **not** a security boundary
  on an owner connection (see milestone 2.0 notes); production must connect as the runtime role.

### 3.2 Request tenant context
1. Session authentication (DRF `SessionAuthentication`, CSRF enforced).
2. Header `X-Company-ID` (UUID) identifies the active company. It is **never** taken from the body.
3. A narrowly scoped `SECURITY DEFINER` SQL function `erp_resolve_company_access(user, company)`
   (owned by the owner role, fixed `search_path`) returns the company's tenant id only if the
   user has an active membership and a role assignment covering that company; otherwise NULL.
   This is the only RLS bypass, it returns a single id, and it is tested for misuse.
4. Missing header on a company-scoped endpoint → 400 `company_required`; unknown company or no
   access → **404** (`not_found`, same as a non-existent company, so existence is not revealed).
5. Inside `transaction.atomic()` (`ATOMIC_REQUESTS=True`): `set_config('app.tenant_id', …, true)`,
   `set_config('app.user_id', …, true)`, `SET LOCAL ROLE somali_erp_app`.
6. Views receive `request.tenant`, `request.company`, `request.membership`, and the resolved
   permission set; querysets come only from selectors that take them explicitly.

### 3.3 RLS policy template
```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <t>
  USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```
Missing setting → NULL → no rows (fail closed). A migration helper generates forward and
reverse SQL so every app applies the same template.

### 3.4 Composite foreign keys
Django has no composite FKs, so migrations add them with `RunSQL` (reversible):
- Each tenant-owned parent gets `UNIQUE (tenant_id, id)`; company-scoped parents also
  `UNIQUE (company_id, id)`.
- Children add `FOREIGN KEY (tenant_id, company_id) REFERENCES companies (tenant_id, id)` and,
  where a row must stay inside one company, `FOREIGN KEY (company_id, branch_id) REFERENCES branches (company_id, id)`.
- The normal Django FK on the single column stays (ORM behaviour, `on_delete`).
- A catalog test fails if a tenant-owned table references another tenant-owned table without
  the composite FK.

### 3.5 Error codes added in Phase 2
`company_required`, `not_found`, `permission_denied`, `not_authenticated`, `invalid_credentials`,
`throttled`, `validation_error`, `csrf_failed`, `last_owner`, `registration_closed`.

### 3.6 Way of working per milestone
1. Back up the development database before applying new migrations:
   `docker compose exec db pg_dump … > backups/<date>-before-<milestone>.sql.gz` (`backups/` is git-ignored).
2. Implement, run backend + frontend checks, verify manually where relevant.
3. One local commit per milestone (no remote). Report actual results.
4. Rollback = `git revert <commit>` + `python manage.py migrate <app> <previous_migration>`
   (all migrations reversible). Reversing a migration drops the tables it created, including
   any development rows in them — the backup from step 1 restores them. **No volume resets.**

## 4. Milestones

Order and dependencies:

```
2.0 DB roles ─► 2.1 Audit log ─► 2.2 Authentication ─► 2.3 Tenancy core + RLS ─► 2.4 Roles & permissions
                                                                                   │
                         2.7 Backend i18n (can start after 2.2) ◄──────────────────┤
                                                                                   ▼
                                   2.5 Branches ─► 2.6 Members & invitations ─► 2.8 Frontend ─► 2.9 Phase close
```

---

### Milestone 2.0 — Database role separation (smallest secure milestone) — ✅ done 2026-10-24

Implementation notes (differences from the plan):
- Role names: owner `somali_erp` (existing), runtime `somali_erp_app`.
- The migration also creates the runtime role as `NOLOGIN` when it does not exist, so a fresh
  database (CI, new developer) can migrate before `ensure_db_roles` runs.
- `SET LOCAL ROLE` on an owner connection was found **not** to stop a switch back to the owner
  (PostgreSQL checks `SET ROLE` against the session user). Escalation tests therefore log in as
  the runtime role; section 3.1's "defence in depth" switch is only a test aid, and production
  safety relies on connecting as the runtime role (now the default).
- Tests use `config.test_settings` (owner role) so pytest can create the test database.
**Why first:** without it, every later RLS policy is bypassed by the superuser connection.
No business tables, no API change, no new dependency.

Scope / files:
- `backend/apps/core/management/commands/ensure_db_roles.py` — idempotent: creates
  `somali_erp_app` if missing, sets its password from env, enforces `NOSUPERUSER NOBYPASSRLS
  NOCREATEDB NOCREATEROLE`; refuses to run if the app role name equals the owner.
- `backend/apps/core/migrations/0001_app_role_grants.py` — grants + default privileges (reverse: revoke).
- `backend/config/settings.py` — credentials chosen by `DJANGO_DB_ROLE`; new env vars
  `POSTGRES_APP_USER`, `POSTGRES_APP_PASSWORD`.
- `docker-compose.yml` — backend command: `ensure_db_roles` → `migrate` (owner) → `runserver` (app).
- `.env.example` (+ the local `.env`, adding the two new keys without changing existing ones),
  `README.md`, `docs/SECURITY.md`.
- `backend/apps/core/tests/test_db_roles.py`, test helper `as_app_role()`.

Migrations: `core.0001_app_role_grants` (RunSQL, reversible). No table changes.

Risks → mitigations:
- App role accidentally powerful → attributes asserted by tests at every run.
- Future tables not granted → default privileges + test that the app role can use every table.
- Password in env → only in git-ignored `.env`; placeholder in `.env.example`; production check
  rejects placeholder passwords.
- Owner is superuser in local Docker → documented as dev-only; production checklist requires a non-superuser owner.

Tests:
- Positive: app role can `SELECT/INSERT/UPDATE/DELETE` on `users` and `django_session`;
  readiness endpoint works when Django connects as the app role; `ensure_db_roles` twice → no error, no change.
- Negative: app role `rolsuper = false`, `rolbypassrls = false`; `CREATE TABLE` → permission
  denied; `DROP TABLE users` → denied; `DELETE FROM django_migrations` → denied; `SET ROLE somali_erp` from the app role → denied.

Acceptance criteria:
- The running backend connects as `somali_erp_app` (verified with `SELECT current_user`
  through `manage.py shell` in the backend container, and by a test using runtime settings).
- All existing 35 backend tests + new tests pass; existing data and volume untouched (migration count only increases).

Rollback: revert commit, `migrate core zero` (revokes grants), set `DJANGO_DB_ROLE=owner`. The
role can stay (harmless) or be dropped manually after `REASSIGN/REVOKE` — documented, not automatic.

---

### Milestone 2.1 — Audit log and request id — ✅ done 2026-10-24

Implementation notes (differences from the plan):
- Columns follow SECURITY.md § 8.3 (adds `outcome`, `actor_type`, `company_id`, `target_type/id`;
  `changes` became `metadata`; no `user_agent` — not needed, personal data). `tenant_id`/`company_id`
  stay plain UUIDs with **no** foreign keys, so audit rows never cascade or block deletions.
- **RLS on `audit_logs` is deferred to 2.3** — no tenant table or tenant context exists yet, so
  a policy could not be tested meaningfully.
- No TRUNCATE trigger: the runtime role has no TRUNCATE privilege, the owner could drop such a
  trigger anyway, and pytest's transactional tests clean tables with TRUNCATE.
- Only event emitted now: `security.db_runtime_role_ensured` (from `ensure_db_roles`), because no
  authentication or tenant endpoints exist yet. 2.2+ add their events to `apps/audit/events.py`.
- Open for 2.2: how failure events survive a rolled-back request transaction (separate
  connection) and trusted proxy handling for client IPs.
- Compose now runs `migrate` before `ensure_db_roles` (the command records an audit event).
Scope / files: new app `apps/audit` (`AuditLog` model, `services.record_event()`),
`apps/core/middleware.py` (`X-Request-ID`: accept a valid UUID or generate one; echoed in the
response; included in logs), settings logging format, tests.

Migrations: `audit.0001` — `audit_logs` (`id bigint identity`, `tenant_id uuid NULL`,
`user_id uuid NULL`, `action`, `object_type`, `object_id`, `changes jsonb`, `ip_address inet`,
`user_agent`, `request_id uuid`, `created_at`); indexes; `REVOKE UPDATE, DELETE` from the app
role; trigger rejecting `UPDATE`/`DELETE` for every role (reversing the migration drops the table); RLS:
read own tenant only; insert allowed for own tenant or `tenant_id IS NULL` (platform events such as failed logins).
`tenant_id` gets its FK to `tenants` in 2.3 (table does not exist yet).

Risks → mitigations: logging secrets (deny-list of fields: password, token, secret, session —
replaced by `"[redacted]"`, tested); log flooding from failed logins (throttling in 2.2);
spoofed request ids (only UUIDs accepted, otherwise regenerated).

Tests: event written with actor/IP/request id; `changes` redacts sensitive keys; app role
cannot update/delete audit rows; trigger blocks owner updates; audit row is rolled back together
with a failed business transaction (same transaction); request id header round-trip; invalid header replaced.

Acceptance: append-only proven at DB level; no secret appears in any audit test payload.
Rollback: revert + `migrate audit zero` (drops the table; dev audit rows lost — backup first).

---

### Milestone 2.2 — Authentication API — ✅ done 2026-10-24

Implementation notes (differences from the plan; approved conditions in brackets):
- Rate limiting uses an own table `rate_limit_counters` with atomic `INSERT … ON CONFLICT …
  RETURNING` (migration `core.0002`) instead of Django's DB cache, whose `incr` is not atomic
  under concurrency [condition 7]. No `createcachetable`.
- Per-account login limits are keyed by account **and** IP, plus a 100/h account-wide cap;
  checks stop at the first exceeded limit [condition 7: lockout DoS].
- Extra limits: password change 5/min + 20/h per user; reset confirm 20/h per IP.
- Next.js proxy measured: it forwards client X-Forwarded-For/X-Real-IP unchanged and adds
  nothing, so proxy trust stays **off**; production must set `DJANGO_TRUSTED_PROXIES`
  explicitly [condition 5].
- Success + audit share one `atomic(durable=True)`; failures recorded after rollback with
  `record_failure_event()`; unstorable failure events go to the CRITICAL log [conditions 1, 6].
- Production startup also requires a real e-mail backend and an https frontend URL.
- No manual test account was created; all verification used automated test users
  [condition 2].
Blocked by: D4, D5, D6 (`argon2-cffi`), D11.

Scope / files: `apps/accounts/` `serializers.py`, `views.py`, `urls.py`, `services.py`
(login, logout, password change, password reset request/confirm), `throttling.py`;
settings (`PASSWORD_HASHERS` Argon2 first, session ages, `CACHES` DB cache, console email backend in dev);
`requirements/base.txt` (+`argon2-cffi`); compose (`createcachetable`).

Endpoints (`/api/v1/auth/`): `GET csrf/` (sets CSRF cookie), `POST login/`, `POST logout/`,
`GET me/`, `POST password/change/`, `POST password/reset/`, `POST password/reset/confirm/`.

Migrations: none for models (cache table via `createcachetable`, idempotent).

Risks → mitigations:
- Credential stuffing → per-IP and per-account throttles (e.g. 5/min, 20/hour per account), generic `invalid_credentials` message, audit `login_failed`.
- Account enumeration → identical responses and similar timing for unknown email / wrong password / inactive user; password-reset always answers 202.
- Session fixation → `login()` rotates the session key; password change keeps the current session and ends the others.
- CSRF → all unsafe methods require the token (tested with `enforce_csrf_checks=True`).
- Weak passwords → Django validators (min length 10, common, numeric, similarity).
- Reset token abuse → Django's signed, time-limited, single-use tokens; invalidated by password change.

Tests:
- Positive: login with correct credentials (email case-insensitive) → 200 + session cookie
  HttpOnly/SameSite=Lax; `me/` returns profile; logout ends session; password change works and
  re-hashes with Argon2; old PBKDF2 hashes upgrade on login; reset flow end-to-end via console mailbox (`mail.outbox`).
- Negative: wrong password, unknown email, inactive user → same 400 body; 6th attempt → 429
  `throttled`; POST without CSRF token → 403 `csrf_failed`; `me/` unauthenticated → 403;
  reused/expired reset token → 400; reset request for unknown email → 202 and no mail; weak new password → 400.

Acceptance: every auth event audited (`login_succeeded`, `login_failed`, `logout`,
`password_changed`, `password_reset_requested/completed`); no endpoint reveals whether an email exists.
Rollback: revert; remove dependency; cache table can stay (unused) or be dropped manually.

---

### Milestone 2.3 — Tenancy core, RLS and active company
Blocked by: D1, D2, D3, D9, D10. (Largest milestone; may be split into 2.3a schema/RLS and 2.3b API if it grows.)

Scope / files:
- New apps: `tenants` (`Tenant`, `Membership`), `organizations` (`Company`, `Branch` model only —
  CRUD comes in 2.5), `finance` (`Currency` reference model seeded with USD, SOS).
- `apps/core/db.py` — RLS and composite-FK migration helpers; `apps/core/tenancy.py` —
  context resolution (header, SECURITY DEFINER lookup, `set_config`, `SET LOCAL ROLE`);
  base view `CompanyScopedAPIView`; `TenantOwnedModel` abstract model.
- `apps/tenants/services.py::register_business()` — one transaction: user, tenant, owner
  membership, company (USD base, `Africa/Mogadishu`, fiscal year start month 1), default branch, audit events.
- Endpoints: `POST /api/v1/auth/register/` (respects `REGISTRATION_OPEN`),
  `GET /api/v1/companies/` (companies the user may access, across tenants, via SECURITY DEFINER function),
  `GET /api/v1/company/` (active company detail, requires `X-Company-ID`).
- Settings: `ATOMIC_REQUESTS = True`.
- Docs: SECURITY/ARCHITECTURE switch from `X-Tenant-ID` to `X-Company-ID`; roadmap D9 change.

Migrations: `finance.0001` (currencies + seed), `tenants.0001` (tenants, memberships),
`organizations.0001` (companies, branches), RLS + composite FKs + SECURITY DEFINER functions
(`RunSQL`, reversible), `audit.0002` (FK `tenant_id → tenants`).

Constraints: `UNIQUE(tenant_id, user_id)` on memberships; `UNIQUE(tenant_id, code)` on companies;
`UNIQUE(company_id, code)` on branches; `UNIQUE(tenant_id, id)` on companies;
`FOREIGN KEY (tenant_id, company_id) → companies(tenant_id, id)` on branches;
`CHECK fiscal_year_start_month BETWEEN 1 AND 12`; status checks.

Risks → mitigations:
- Cross-tenant read/write → RLS + selectors + 404 policy; composite FKs for references.
- SECURITY DEFINER misuse → returns one tenant id only for a verified membership, fixed
  `search_path`, `EXECUTE` granted only to the app role, tested with forged inputs.
- Settings leaking across pooled connections → `set_config(..., true)` and `SET LOCAL` are
  transaction-scoped; test runs two requests for different tenants on one connection.
- Registration spam → `REGISTRATION_OPEN` flag, throttle (same store as login), audit.
- Partial registration → single transaction; failure injection test.

Tests:
- Positive: registration creates exactly one of each object with the user as owner; user lists
  only their companies; active company resolves with valid header; a user with two tenants sees
  both and can switch per request.
- Negative / attacks: missing header → 400; header with another tenant's company → 404; header
  with random UUID → 404 (same body); malformed header → 400; disabled membership → 404;
  registration closed → 403; failure after company insert → nothing persisted.
- RLS (DB level, as app role): with tenant A set, `SELECT` on companies/branches/memberships
  returns no B rows; `INSERT` with B's `tenant_id` → policy violation; no setting → zero rows;
  `UPDATE … SET tenant_id = B` → rejected.
- Composite FK (as owner, RLS bypassed): branch with `tenant_id` A and `company_id` of tenant B → FK violation.
- Catalog tests: every `TenantOwnedModel` table has RLS enabled + forced + policy; every
  tenant-to-tenant reference has a composite FK.

Acceptance: all of the above green; manual check: two registered businesses cannot see each
other through any endpoint. Rollback: revert + migrate the three apps to zero (dev data in them lost; backup first).

---

### Milestone 2.4 — Roles and permissions with server-side enforcement
Blocked by: D7.

Scope / files: `apps/accounts` or `apps/tenants`: `Permission` (global catalog), `Role`,
`RolePermission`, `MembershipRole` (optional `company_id`); `permissions.py` (catalog in code,
synced by migration); DRF permission class `HasCompanyPermission` using a view's
`required_permissions = {"GET": "...", "POST": "..."}`; role templates seeded for every tenant
(registration + data migration for existing tenants); endpoints: list permissions, list/create/update/delete
custom roles, view own effective permissions (`GET /api/v1/company/permissions/`).

Migrations: tables + RLS + composite FKs (`membership_roles (tenant_id, membership_id)`,
`(tenant_id, role_id)`, `(tenant_id, company_id)`), unique constraints, seed data migration.

Risks → mitigations: privilege escalation (grant only permissions you hold; Owner role
immutable; cannot remove the last Owner → 409 `last_owner`; cannot edit your own roles);
forgotten checks (test enumerates every URL pattern and fails if a view has no
`required_permissions` and is not on an explicit public allow-list); stale permission cache
(resolved once per request, never cached across requests in Phase 2).

Tests: owner can do everything; Viewer gets 403 on writes; company-limited role → 404 for other
companies of the same tenant; escalation attempts (grant unheld permission, edit own role,
delete last owner, assign role of another tenant) all rejected; role changes audited.
Acceptance: the "every view declares a permission" test is green and enforced from here on.
Rollback: revert + migrate to previous; seeded rows removed with the tables.

---

### Milestone 2.5 — Branch management (first fully guarded resource)
Scope / files: `apps/organizations` `selectors.py`, `services.py`, `serializers.py`, `views.py`;
`/api/v1/branches/` list/create/retrieve/update/archive (no hard delete); company settings
update (name, timezone; base currency immutable once postings exist — no postings yet, so
locked after creation in Phase 2 ★ to be safe). Shared test helper
`assert_cross_tenant_isolation(endpoint, …)` reused by every later module.

Migrations: none or small (e.g. `is_active` default) — branches table exists since 2.3.

Risks → mitigations: IDOR on branch ids (selectors scoped by company; 404); mass assignment
(`tenant_id`, `company_id` read-only, taken from context); duplicate codes (unique constraint → 400).

Tests: CRUD as Administrator; Viewer read-only; other tenant's branch id → 404 for
GET/PATCH/archive; body containing another `company_id`/`tenant_id` is ignored; duplicate code → 400; audit with field diff.
Acceptance: isolation helper green for every branch endpoint. Rollback: revert (no schema).

---

### Milestone 2.6 — Members and invitations
Blocked by: D3.

Scope / files: `Invitation` model (token **hash** stored, expiry 7 days, single use, email,
role, optional company), endpoints: create/list/revoke invitations, accept invitation (creates
the user if needed, else links the existing account after login), list members, disable member,
change member roles. Invitation link shown to the admin (copy/share) and sent by email backend.

Migrations: `invitations` table + RLS + composite FKs.

Risks → mitigations: token theft (only a hash stored; high-entropy token; expiry; single use;
revocable); invitation to an existing user hijacking (acceptance requires logging in as that
email); disabling yourself/last owner (blocked); member enumeration across tenants (RLS + 404).

Tests: full invite → accept → access flow; expired, revoked, reused, wrong-email tokens rejected;
disabled member loses access on next request; all actions audited.
Acceptance: a second user can join a company only through a valid invitation. Rollback: revert + migrate.

---

### Milestone 2.7 — Backend localization (Somali / English)
Blocked by: D6 (`gettext`), D12 (review process). Can run in parallel after 2.2.

Scope / files: settings (`LocaleMiddleware`, `LANGUAGES`, register `so` in `LANG_INFO`,
`LOCALE_PATHS`), language resolution order: authenticated user's `preferred_language` →
`Accept-Language` → default ★ Somali (D8); `backend/locale/so/LC_MESSAGES/django.po`;
Dockerfile installs `gettext` and runs `compilemessages`; `.mo` files built, not committed;
`PATCH /api/v1/auth/me/` for `preferred_language`.

Migrations: none.

Risks → mitigations: untranslated or wrong Somali text (fallback to English; review markers;
test that every msgid has a Somali entry or is on a tracked "pending" list); error `code`s stay
language-neutral so the frontend never parses messages.

Tests: same error in `so` and `en`; unknown language falls back; user preference beats header;
error codes identical across languages; catalog completeness test.
Acceptance: all Phase 2 user-facing API messages available in both languages (Somali marked pending review where applicable).
Rollback: revert; image rebuild.

---

### Milestone 2.8 — Frontend foundations and Phase 2 screens
Blocked by: D8.

Scope / files: `src/lib/api.ts` (fetch wrapper: CSRF token, `X-Company-ID`, error envelope,
401/403/404 handling), `src/lib/i18n/` (`so.ts`, `en.ts`, typed keys, `Intl` formatters),
`src/middleware.ts` (redirect unauthenticated users to login), screens: login, register,
company picker, branches list/create/edit, members & invitations, language switch, logout.
Active company stored in a cookie and sent as header (server still verifies every request).

Migrations: none.

Risks → mitigations: frontend treated as security boundary (never — all checks server-side,
tests prove API rejects what the UI hides); XSS (React escaping, no `dangerouslySetInnerHTML`,
CSP header added); CSRF (token from cookie sent as header); open redirects after login (only relative internal paths).

Tests: Vitest for API client (error envelope, CSRF header, company header), i18n (every key in
both dictionaries — type-checked + test), components (login errors shown in both languages);
manual end-to-end walkthrough recorded in the report. (Browser E2E tooling is a Phase 6 decision.)
Acceptance: a new business can register, log in, pick a company, manage branches and invite a
member, in Somali or English. Rollback: revert (no schema).

---

### Milestone 2.9 — Phase closing
Scope: full security sweep (permission-declared test, RLS catalog test, composite-FK test,
isolation helper on every endpoint), `check --deploy`, docs updated (ARCHITECTURE, SECURITY,
DATABASE_DESIGN, ROADMAP Phase 2 → done), clean-checkout verification as in Phase 1, final local commit.
Acceptance = roadmap Phase 2 criteria (updated for D9: warehouse moved to Phase 3).

## 5. What will not be in Phase 2
Two-factor authentication (Phase 6), real email/SMS providers, subscriptions/billing, API tokens
for integrations (Phase 7), Django admin exposure (stays disabled), warehouses (Phase 3).
