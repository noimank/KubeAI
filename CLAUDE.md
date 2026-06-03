# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KubeAI is a Kubernetes-native AI/ML platform with multi-tenant RBAC. Monorepo with FastAPI backend (`backend/`) and React frontend (`frontend/`). Deployed via Helm chart (`infra/helm/kubeai/`). All user-facing text is in Chinese (zh-CN) — no i18n library, strings are hardcoded.

## Development Commands

### Backend (from `backend/`)

```bash
uv sync
uv run uvicorn app.main:app --reload          # dev server (port 8000)
uv run pytest                                  # all tests
uv run pytest tests/unit/test_security.py::test_hash_password -v  # single test
uv run alembic upgrade head                    # migrate
uv run alembic revision --autogenerate -m "description"
uv run ruff check . && uv run ruff format .    # lint+format
uv run mypy app/                               # type check
```

### Frontend (from `frontend/`)

```bash
pnpm install
pnpm dev                    # dev server (port 3000, proxies /api → localhost:8000)
pnpm build                  # tsc -b then vite build
pnpm lint && pnpm format
pnpm typecheck
pnpm test
```

### Infrastructure & Docs (from project root)

```bash
# Helm deploy (PostgreSQL, Redis, MinIO, Volcano, Harbor, JupyterHub, Prometheus stack, backend, frontend)
helm install kubeai infra/helm/kubeai/ -f infra/helm/kubeai/values-dev.yaml -n kubeai --create-namespace

# Docker build
docker build -t kubeai-backend -f infra/images/backend/Dockerfile .
docker build -t kubeai-frontend -f infra/images/frontend/Dockerfile .

# Docs (from backend/)
uv sync --group docs
uv run mkdocs serve --config-file ../mkdocs.yml
```

Pre-commit hooks (ruff+mypy on backend, eslint+prettier+tsc on frontend): `pre-commit install` then auto-runs on commit. Config: `.pre-commit-config.yaml`.

## Architecture

### Backend (`backend/`)

- **Entry point**: `app/main.py` — FastAPI app with lifespan, middleware stack (RequestId → Tenant → error handlers), routers at `/api` prefix
- **Config**: `app/core/config.py` — Pydantic Settings from `.env`
- **Database**: async SQLAlchemy 2.0 (`DeclarativeBase`, `Mapped`/`mapped_column`). All models use `TimestampMixin`; User adds `SoftDeleteMixin`. Migrations in `alembic/` (async runner via asyncpg)
- **Auth**: JWT access/refresh (HS256, `app/core/security.py`). Token blacklist via Redis (`token_blacklist.py`). Account lockout after 5 failures (Redis TTL 15 min)
- **RBAC**: Casbin (`app/core/casbin.py`, model at `rbac_model.conf`). Roles: admin > mlops > engineer > annotator. `manage` action is wildcard in matcher. Policies seeded from `permissions.py`
- **Dependency injection**: `app/api/deps.py` — `CurrentUser` (JWT + blacklist check), `require_permission(resource, action)`, `require_tenant_access()`. **Critical**: `get_db()` exists in both `core/database.py` and `api/deps.py` — endpoints must use `deps.py`
- **API pattern**: All responses wrapped in `BaseResponse[T]` (`{success, message, data}`). `AppException` hierarchy in `core/exceptions.py` caught by middleware
- **Services**: Constructor-injected with `AsyncSession` (+ optional Redis/MinIO). All in `app/services/` — covering auth, tenants, datasets, training jobs (Volcano VCJobs), inference (KServe + KEDA), experiments (MLflow), annotations (Label Studio), dev environments (JupyterHub), images (Harbor), algorithms, monitoring, notifications, dashboard, audit. Model registry has no dedicated service — logic is in the endpoint module directly
- **Multi-tenancy**: DB (`TenantMixin` + FK) → app (`TenantMiddleware` + `require_tenant_access`) → infra (K8s NetworkPolicy per namespace)
- **Integrations** (`app/integrations/`): `k8s/` (async kubernetes_asyncio), `volcano/` (VCJob CRDs), `kserve/` + `keda/` (inference CRDs), `harbor/`, `minio/`, `mlflow/`, `jupyterhub/`, `labelstudio/`, `prometheus/` (DCGM GPU metrics), `storage/` (local filesystem). K8s calls are fully async; MinIO/Harbor/MLflow clients are sync — wrap in `asyncio.to_thread()` at service layer. Namespace prefix: `kubeai-`
- **WebSocket**: `WS /api/ws?token=<jwt>`. Connection manager (`ws_manager.py`) groups by tenant+user (max 5/user). Redis Pub/Sub (`ws_pubsub.py`) bridges multi-replica broadcast on `kubeai:*` channels
- **Startup** (`core/events.py`): seeds admin (`admin`/`Admin123456`), initializes Redis/Casbin/all external clients, starts background tasks (idle checker, resource cleaner, quota alerts, metrics push)
- **Tests**: `asyncio_mode = "auto"`. `conftest.py` provides `httpx.AsyncClient` with `ASGITransport` for in-process testing. Unit in `tests/unit/`, integration in `tests/integration/`
- **Mounted routers**: auth, algorithms, annotations, audit_logs, credentials, dashboard, datasets, dev_environment_images, dev_environments, experiments, images, inference_proxy, inference_services, model_registry, monitoring, notifications, tenants, training_jobs, users

### Frontend (`frontend/`)

- **Stack**: React 18 + TypeScript (strict) + Ant Design 5 + ProComponents + Zustand + TanStack React Query + Tailwind CSS
- **Build**: Vite 6, `@` alias → `src/`, chunk splitting for vendor/antd/router
- **Routing**: React Router v7, all pages lazy-loaded in `App.tsx`. `AuthGuard` → `MainLayout` (ProLayout sidebar + header) → `PermissionGuard` per route
- **State**: 6 Zustand stores (`auth`, `rbac`, `tenant`, `theme`, `notification`, `ws`). Cross-store via `useOtherStore.getState()`. WebSocket reconnect with exponential backoff; events invalidate React Query caches by domain (training, inference, dev_environment, cluster_resource)
- **API client**: `src/services/api.ts` — Axios with recursive snake_case↔camelCase transform. Auto token refresh queues concurrent 401s. `messageHolder.ts` bridges Ant Design `message` to interceptors
- **RBAC**: `resource:action` strings (e.g., `datasets:read`). Admin gets `*`. Route-level via `PermissionGuard`, sidebar visibility via `filterMenuItems()`
- **Tailwind**: Preflight disabled (coexist with Ant Design). Dark mode via `[data-theme="dark"]` selector. CSS variables for status colors in `styles/variables.css`
- **Tests**: Vitest + jsdom + @testing-library/react. Files mirror `src/` under `tests/`

### Infrastructure (`infra/`)

- **Helm**: `infra/helm/kubeai/` — 10 chart dependencies (PostgreSQL, Redis, MinIO, Volcano, Harbor, kube-prometheus-stack, DCGM exporter, JupyterHub, backend, frontend)
- **Images**: Backend/frontend + Jupyter/VS Code/RStudio dev-environment images in `infra/images/`
- **CI/CD**: `.github/workflows/` — `ci.yml` (PR: lint+test), `build.yml` (push to main/dev: GHCR images), `release.yml` (v* tag: versioned images + Helm package)

## Key Conventions

- Backend: Python 3.12+, Ruff (line-length 120, double quotes), mypy strict
- Frontend: pnpm, ESLint 9 flat config, Prettier (no semicolons, single quotes, 100 char width, 2-space indent)
- API: backend snake_case ↔ frontend camelCase (auto-transformed)
- Commits: emoji-prefixed Conventional Commits (`✨ feat:`, `🔧 chore:`, `♻️ refactor:`). See `AGENTS.md`
- K8s: fully async via `kubernetes_asyncio`. Sync external clients (MinIO, Harbor, MLflow) wrapped in `asyncio.to_thread()`
