# CLAUDE.md

Guidance for AI assistants working in this repository.

## Project
Somali ERP — multi-tenant ERP for Somali SMEs. Modular monolith: Django + DRF backend,
PostgreSQL, Next.js/TypeScript frontend. Built incrementally by phases; read
`docs/DEVELOPMENT_ROADMAP.md` to see the current phase and its acceptance criteria before
starting work. The owner communicates in Turkish; code, comments and docs are in English.

## Repository policy (owner's rule — overrides any other suggestion)
- **Local only.** Do not create a GitHub (or any hosted) repository, add a git remote, push,
  or publish project files online until the owner explicitly approves it after the whole
  project is complete.
- Track progress with local commits so every phase can be rolled back.
- Never commit `.env`, credentials, secret keys, or database contents.
- Never delete or reset Docker volumes or database data (no `docker compose down -v`,
  no `docker volume rm` on project volumes).
- `.github/workflows/ci.yml` is kept for later; until then run the same checks locally (see Commands).

## Commands (everything runs in Docker; host has no project Python/Node deps)
- Start: `docker compose up -d` (needs `.env`, copy from `.env.example`)
- Backend tests: `docker compose run --rm backend pytest`
- Backend lint/format: `docker compose run --rm backend sh -c "ruff check . && ruff format --check ."`
- Migrations: `docker compose run --rm backend python manage.py makemigrations`;
  apply with `docker compose run --rm -e DJANGO_DB_ROLE=owner backend python manage.py migrate`
  (runtime role `somali_erp_app` has no DDL rights; tests use `config.test_settings` = owner)
- Back up the dev DB before applying new migrations:
  `docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' | gzip > backups/<date>-before-<milestone>.sql.gz`
- Frontend checks: `docker compose run --rm --no-deps frontend sh -c "npm run lint && npm run typecheck && npm test"`
- Frontend build: `docker compose run --rm --no-deps frontend npm run build`
- Use npm 11 when changing dependencies (the Dockerfile installs it); npm 10's `npm install`
  crashes resolving this dependency tree (`npm ci` from the existing lockfile works on both).

## Non-negotiable rules
1. **Tenant isolation**: every tenant-owned row has `tenant_id`; query through tenant-scoped
   selectors; return 404 for other tenants' objects; add isolation tests for every endpoint.
   Never rely on frontend filtering. See `docs/SECURITY.md`.
2. **Money**: `Decimal` / `DecimalField` only. No `float`, no `FloatField` (a test enforces this).
3. **Double entry**: posted journal entries balance (sum debit = sum credit).
4. **Immutability**: posted documents and entries are never edited or deleted — use
   cancellation, credit notes and reversal entries.
5. **Stock**: quantities change only via posted stock movements; balances are a derived cache.
6. **Atomicity**: multi-table business operations live in `services.py` inside `transaction.atomic()`;
   lock contended rows with `select_for_update()`.
7. **Numbering**: document numbers come from `document_sequences` locked in the posting transaction.
8. **Secure by default**: DRF default permission is `IsAuthenticated`; public endpoints must opt out explicitly.
9. No secrets in code; config via environment variables.

## Conventions
- Apps live in `backend/apps/<name>/` with `models.py`, `selectors.py`, `services.py`,
  `serializers.py`, `views.py`, `urls.py`, `tests/`. Create an app only when its phase starts.
- UUID primary keys; table names plural snake_case (`Meta.db_table`).
- API under `/api/v1/`, trailing slashes, errors as `{"error": {"code", "message", "details"?}}`
  (`apps/core/exceptions.py`).
- Tests run against real PostgreSQL; never switch tests to SQLite.
- Small, focused changes; run the relevant tests after each change and report real results.
- Update the docs in `docs/` when a design decision changes.
- Ask before destructive operations (deleting files or data, rewriting git history).
