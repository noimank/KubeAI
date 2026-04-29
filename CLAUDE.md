# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KubeAI is a Kubernetes-native AI/ML platform with multi-tenant RBAC. Monorepo with FastAPI backend (`backend/`) and React frontend (`frontend/`). All user-facing text is in Chinese (zh-CN) — no i18n library, strings are hardcoded.

## Development Commands

### Backend (from `backend/`)

```bash
# Install dependencies
uv sync

# Run dev server (port 8000)
uv run uvicorn app.main:app --reload

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/unit/test_security.py

# Run a single test function
uv run pytest tests/unit/test_security.py::test_hash_password -v

# Database migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"

# Lint & format
uv run ruff check .
uv run ruff check --fix .
uv run ruff format .

# Type check
uv run mypy app/
```

### Frontend (from `frontend/`)

```bash
# Install dependencies
pnpm install

# Run dev server (port 3000, proxies /api → localhost:8000)
pnpm dev

# Build
pnpm build

# Lint & format
pnpm lint
pnpm format

# Type check
pnpm typecheck

# Run tests
pnpm test
pnpm test:watch
```

### Infrastructure (from project root)

```bash
# Start PostgreSQL 17 + Redis 7 (data persisted to ./data/)
docker compose -f docker-compose.dev.yml up -d
```

## Architecture

### Backend (`backend/`)

- **Framework**: FastAPI with async SQLAlchemy (asyncpg + PostgreSQL), Redis for caching/token blacklist
- **Entry point**: `app/main.py` — creates FastAPI app, registers middleware and router at `/api` prefix
- **Config**: `app/core/config.py` — Pydantic Settings, reads from `.env` file
- **Database**: async SQLAlchemy 2.0 with `DeclarativeBase`, `Mapped`/`mapped_column` style. All models use `TimestampMixin`. User has `SoftDeleteMixin`. Models in `app/models/`, migrations in `alembic/` (async runner)
- **Auth flow**: JWT access/refresh tokens (HS256). `app/core/security.py` for hashing and token creation. `app/core/token_blacklist.py` uses Redis to revoke tokens by JTI. Account lockout after 5 failed attempts (Redis TTL 15 min)
- **RBAC**: Casbin enforcer (`app/core/casbin.py`) with policy model at `app/core/rbac_model.conf`. Roles: admin > mlops > engineer > annotator. Policies seeded from `app/core/permissions.py`. `manage` action in Casbin matcher matches all actions
- **Dependency injection**: `app/api/deps.py` — `CurrentUser` (JWT auth + blacklist check), `require_permission(resource, action)`, `require_tenant_access()`. Note: `get_db()` is defined in both `app/core/database.py` and `app/api/deps.py`; endpoints use the one in `deps.py`
- **Services**: Constructor-injected with `AsyncSession` (and optionally Redis). `AuthService` handles register/login/lockout/refresh/logout. `TenantService` orchestrates K8s namespace + ResourceQuota + NetworkPolicy with rollback on failure. `CredentialService` is a sync wrapper around K8s Secrets (no DB). `OAuthService` handles OIDC/OAuth2 via authlib with Redis-cached discovery docs
- **Multi-tenancy**: Three layers — DB-level (`TenantMixin` + FK), app-level (`TenantMiddleware` + `require_tenant_access`), infra-level (K8s NetworkPolicy per namespace isolating tenant traffic)
- **K8s integration**: `app/integrations/k8s/` wraps the synchronous `kubernetes` Python client (CoreV1Api, NetworkingV1Api) with `@with_retry` exponential backoff. Namespace prefix: `kubeai-`. **Important**: K8s calls are synchronous — they block the async event loop
- **API responses**: All endpoints return `BaseResponse[T]` wrapper (`{success, message, data}`)
- **Exceptions**: `AppException` hierarchy in `app/core/exceptions.py` — caught by error handler middleware returning `BaseResponse` with appropriate HTTP status. All default messages are in Chinese
- **Tests**: `asyncio_mode = "auto"` in pytest config. `conftest.py` provides session-scoped `event_loop` + `httpx.AsyncClient` with `ASGITransport` for in-process testing. Unit tests in `tests/unit/`, integration in `tests/integration/`
- **Stubs**: Many endpoint files exist in `app/api/endpoints/` (datasets, training_jobs, etc.) but are **not yet mounted** in `router.py` — only `auth`, `credentials`, and `tenants` routers are active

### Frontend (`frontend/`)

- **Stack**: React 18 + TypeScript (strict) + Ant Design 5 + ProComponents + Zustand + TanStack React Query + Tailwind CSS
- **Build**: Vite 6 with `@` path alias to `src/`, manual chunk splitting (`vendor`, `antd`, `router`)
- **Routing**: React Router v7 with lazy-loaded pages. Routes defined declaratively in `App.tsx`. `AuthGuard` wraps authenticated routes, `PermissionGuard` wraps per-route permission checks
- **State**: Zustand stores using flat `create()` pattern, no middleware. Cross-store communication via `useOtherStore.getState()` (e.g., authStore sets rbacStore role on login). Stores: `authStore`, `rbacStore`, `tenantStore`, `themeStore`
- **RBAC permissions**: Strings follow `resource:action` pattern (e.g., `datasets:read`, `tenants:manage`). Admin gets wildcard `*`. Enforced at route level (`PermissionGuard`) and sidebar visibility
- **API client**: `src/services/api.ts` — Axios instance with recursive snake_case↔camelCase key transform on requests/responses. Auto token refresh with queue for concurrent 401s. `messageHolder.ts` singleton bridges Ant Design `message` API to non-React code (interceptors)
- **Token storage**: Dual-persisted in localStorage (cross-tab persistence, interceptor access) and Zustand state (React reactivity)
- **Tailwind**: Preflight disabled to coexist with Ant Design. Dark mode via `[data-theme="dark"]` attribute selector
- **Tests**: Vitest with jsdom, `@testing-library/react`. Test files mirror `src/` structure under `tests/`

### Key Conventions

- Backend API uses snake_case; frontend auto-transforms to camelCase
- All API responses wrapped in `BaseResponse` (`{success, message, data}`)
- Backend: Python 3.12+, Ruff (line-length 120, double quotes), mypy strict with pydantic plugin
- Frontend: pnpm, ESLint 9 flat config, Prettier (no semicolons, single quotes, 100 char width, 2-space indent), Vitest
