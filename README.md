# Somali ERP

A modular, multi-tenant ERP platform for small and medium-sized businesses in Somalia:
sales, purchasing, inventory, double-entry accounting, payments (including mobile money
recording), USD/SOS multi-currency, and a Somali/English interface.

> **Status:** Phase 1 (project scaffold). There are no business features yet. See the
> [roadmap](docs/DEVELOPMENT_ROADMAP.md).

## Documentation

| Document | Contents |
|---|---|
| [Product requirements](docs/PRODUCT_REQUIREMENTS.md) | Users, scope, functional and non-functional requirements |
| [Architecture](docs/ARCHITECTURE.md) | Modules, layering, conventions, pinned versions, decisions |
| [Database design](docs/DATABASE_DESIGN.md) | Tables, keys, constraints, tenant boundaries, posting flows |
| [Security](docs/SECURITY.md) | Tenant isolation, authentication, authorization, controls |
| [Roadmap](docs/DEVELOPMENT_ROADMAP.md) | Phases, acceptance criteria, open decisions |

## Stack

Django 5.2 LTS + Django REST Framework · PostgreSQL 17 · Next.js 16 + React 19 + TypeScript ·
Docker Compose for local development · pytest, Vitest, Ruff, ESLint · GitHub Actions workflow
(kept for later; the repository is local-only until publishing is approved).

## Getting started

Requirements: Docker Desktop (with Docker Compose v2) and Git. Nothing else needs to be
installed on the host — Python and Node run inside containers.

```bash
cp .env.example .env          # development defaults; edit ports if they clash
docker compose up --build     # first run builds images and applies migrations
```

| Service | URL |
|---|---|
| Web app (status page) | http://localhost:3000 |
| API liveness | http://localhost:8000/api/v1/health/ |
| API readiness (checks DB) | http://localhost:8000/api/v1/health/ready/ |
| OpenAPI schema | http://localhost:8000/api/schema/ |
| Swagger UI (development only) | http://localhost:8000/api/docs/ |
| PostgreSQL | `localhost:5433` (user/password from `.env`) |

The web app proxies `/api/*` to Django, so `http://localhost:3000/api/v1/health/` works too.

Authentication API (session cookies + CSRF): `/api/v1/auth/` — `csrf/`, `login/`, `logout/`,
`me/`, `password/change/`, `password/reset/`, `password/reset/confirm/`. Details and limits in
[docs/SECURITY.md § 3](docs/SECURITY.md#3-authentication-implemented-in-milestone-22).
In development, password-reset e-mails are printed to the backend log (`docker compose logs backend`).

Database roles: migrations run as the owner role (`POSTGRES_USER`); the web process connects
as the restricted runtime role (`POSTGRES_APP_USER`), which cannot change the schema or bypass
row-level security. Startup runs `ensure_db_roles` and `migrate` as the owner automatically.
If you already had a `.env`, add `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD` from `.env.example`.

## Everyday commands

```bash
# Backend
docker compose run --rm backend pytest                     # tests (real PostgreSQL)
docker compose run --rm backend ruff check .               # lint
docker compose run --rm backend ruff format .              # format
docker compose run --rm backend python manage.py makemigrations
# Schema changes need the owner role; the default runtime role has no DDL rights.
docker compose run --rm -e DJANGO_DB_ROLE=owner backend python manage.py migrate

# Frontend
docker compose run --rm --no-deps frontend npm test        # Vitest
docker compose run --rm --no-deps frontend npm run lint
docker compose run --rm --no-deps frontend npm run typecheck
docker compose run --rm --no-deps frontend npm run build

# After changing frontend/package.json
docker compose build frontend && docker compose up -d --renew-anon-volumes frontend

# Stop everything (database data is kept in the pgdata volume)
docker compose down
# Never add -v unless you really want to delete the local database.
```

## Repository layout

```
backend/    Django project (config/ settings, apps/ modules, tests/)
frontend/   Next.js app (src/app routes, src/components, src/lib)
docs/       Requirements, architecture, database, security, roadmap
.github/    CI workflow
```

## Troubleshooting

- **Port already in use** — change `DB_HOST_PORT`, `BACKEND_HOST_PORT` or `FRONTEND_HOST_PORT` in `.env`.
  The database uses host port 5433 by default because 5432 is often taken by a local PostgreSQL.
- **Unknown API URL shows an HTML page** — expected in development (`DJANGO_DEBUG=true`); with debug off it returns the JSON error format.
- **Project inside OneDrive** — works, but sync can lock files and slow Docker bind mounts. A folder outside OneDrive (e.g. `C:\dev\somali-erp`) is recommended.
