# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KubeAI is a Kubernetes-native AI/ML platform with multi-tenant RBAC. Monorepo with FastAPI backend (`backend/`) and React frontend (`frontend/`).

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

# Lint
uv run ruff check .
uv run ruff check --fix .

# Type check
uv run mypy app/

# Format
uv run ruff format .
```

### Frontend (from `frontend/`)

```bash
# Install dependencies
pnpm install

# Run dev server (port 3000, proxies /api → localhost:8000)
pnpm dev

# Build
pnpm build

# Lint
pnpm lint

# Type check
pnpm typecheck

# Format
pnpm format

# Run tests
pnpm test
pnpm test:watch
```

### Infrastructure

```bash
# Start PostgreSQL + Redis (from project root)
docker compose -f docker-compose.dev.yml up -d
```

## Architecture

### Backend (`backend/`)

- **Framework**: FastAPI with async SQLAlchemy (asyncpg + PostgreSQL), Redis for caching/token blacklist
- **Entry point**: `app/main.py` — creates FastAPI app, registers middleware and router at `/api` prefix
- **Config**: `app/core/config.py` — Pydantic Settings, reads from `.env` file
- **Database**: async SQLAlchemy with `DeclarativeBase`. All models use `TimestampMixin`. User has `SoftDeleteMixin`. Models in `app/models/`, migrations in `alembic/`
- **Auth flow**: JWT access/refresh tokens (HS256). `app/core/security.py` for hashing and token creation. `app/core/token_blacklist.py` uses Redis to revoke tokens by JTI. Account lockout after 5 failed attempts (Redis TTL 15 min)
- **RBAC**: Casbin enforcer (`app/core/casbin.py`) with policy model at `app/core/rbac_model.conf`. Roles: admin > mlops > engineer > annotator. Policies seeded from `app/core/permissions.py`. `manage` action in Casbin matcher matches all actions
- **Dependency injection**: `app/api/deps.py` — `CurrentUser` (JWT auth + blacklist check), `require_permission(resource, action)`, `require_tenant_access()`
- **Multi-tenancy**: `TenantMiddleware` sets `request.state.tenant_id`. `TenantMixin` on models for tenant-scoped data. Admin bypasses tenant checks
- **K8s integration**: `app/integrations/k8s/` wraps Kubernetes client (CoreV1Api, NetworkingV1Api) with retry logic. Namespace prefix: `kubeai-`
- **API responses**: All endpoints return `BaseResponse[T]` wrapper (`{success, message, data}`)
- **Exceptions**: `AppException` hierarchy in `app/core/exceptions.py` — caught by error handler middleware returning `BaseResponse` with appropriate HTTP status

### Frontend (`frontend/`)

- **Stack**: React 18 + TypeScript + Ant Design 5 + ProComponents + Zustand + React Query + Tailwind CSS
- **Build**: Vite 6 with `@` path alias to `src/`
- **Routing**: React Router v7 with lazy-loaded pages. Routes defined in `App.tsx`. `AuthGuard` wraps authenticated routes, `PermissionGuard` wraps per-route permission checks
- **State**: Zustand stores — `authStore` (user/tokens), `rbacStore` (role/permissions), `tenantStore`, `themeStore` (dark/light mode)
- **API client**: `src/services/api.ts` — Axios instance with snake_case→camelCase key transform on requests/responses. Auto token refresh with queue for concurrent requests
- **Sidebar**: `src/layouts/components/Sidebar.tsx` — menu items filtered by user's RBAC permissions

### Key Conventions

- Backend API uses snake_case; frontend auto-transforms to camelCase
- All API responses wrapped in `BaseResponse` (`{success, message, data}`)
- Backend Python 3.12+, Ruff for linting/formatting (line-length 120), mypy for type checking
- Frontend uses pnpm, ESLint + Prettier, vitest for testing
- User messages/UI text is in Chinese (zh-CN)
