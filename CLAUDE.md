# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KubeAI is a Kubernetes-native AI/ML platform with multi-tenant RBAC. Monorepo with FastAPI backend (`backend/`) and React frontend (`frontend/`). All user-facing text is in Chinese (zh-CN) — no i18n library, strings are hardcoded.

**部署方式**:
- **本地开发**: Helm chart (`infra/helm/kubeai/`) 仅用于本地开发环境，一键部署完整依赖链（PostgreSQL, Redis, MinIO, Volcano, Harbor, APISIX, Prometheus stack, backend, frontend）
- **生产环境**: `infra/k8s/` 下的 K8s manifests 为生产专用，所有生产配置部署在 `kubeai-prod-env` 服务器的 `/root/kubeai` 目录下

## Development Commands

### Backend (from `backend/`)

```bash
uv sync
uv run uvicorn app.main:app --reload          # dev server (port 8000)

# Taskiq background tasks (must run alongside API for dev environments, inference, etc.)
uv run taskiq worker app.core.taskiq_app:broker --fs-discover           # consumes async tasks
uv run taskiq scheduler app.core.taskiq_app:scheduler --skip-first-run  # fires scheduled tasks

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
# Helm 仅用于本地开发部署（请勿用于生产环境）
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
- **Auth**: JWT access/refresh (HS256, `app/core/security.py`). Token blacklist via Redis (`token_blacklist.py`). Account lockout after 5 failures (Redis TTL 15 min). **Identity resolution** unified in `app/core/identity.py` (`IdentityResolver`): decode → blacklist → Redis-cached `TokenIdentity` (`user_token_version` / `tenant_status` provide active invalidation on user/tenant disable). All entrypoints (FastAPI deps / WebSocket / APISIX forward-auth) share this single pipeline
- **RBAC**: Casbin (`app/core/casbin.py`, model at `rbac_model.conf`). Roles: admin > mlops > engineer > annotator. `manage` action is wildcard in matcher. Policies seeded from `permissions.py`
- **Dependency injection**: `app/api/deps.py` — `CurrentUser` (`TokenIdentity` via `IdentityResolver`), `CurrentUserEntity` (full User ORM, only for profile/password write endpoints), `require_permission(resource, action)`, `require_tenant_access()`. **Critical**: `get_db()` exists in both `core/database.py` and `api/deps.py` — endpoints must use `deps.py`
- **API pattern**: All responses wrapped in `BaseResponse[T]` (`{success, message, data}`). `AppException` hierarchy in `core/exceptions.py` caught by middleware
- **Services**: Constructor-injected with `AsyncSession` (+ optional Redis/MinIO). All in `app/services/` — covering auth, tenants, datasets, training jobs (Volcano VCJobs), inference (native Deployment + KEDA; model weights pulled at runtime by a `minio/mc` initContainer), experiments (MLflow), annotations (Label Studio), dev environments (native K8s Pod + APISIX routing), images (Harbor), algorithms, monitoring, notifications, dashboard, audit. Model registry has no dedicated service — logic is in the endpoint module directly
- **Multi-tenancy**: DB (`TenantMixin` + FK) → app (`TenantMiddleware` + `require_tenant_access`) → infra (K8s NetworkPolicy per namespace)
- **Integrations** (`app/integrations/`): `k8s/` (async kubernetes_asyncio — incl. `dev_pod.py` native dev-environment pods and the inference Deployment/initContainer builders), `volcano/` (VCJob CRDs), `keda/` (inference ScaledObjects — GPU-util autoscaling via DCGM), `harbor/`, `minio/`, `mlflow/`, `labelstudio/`, `prometheus/` (DCGM GPU metrics), `storage/` (local filesystem). K8s calls are fully async; MinIO/Harbor/MLflow clients are sync — wrap in `asyncio.to_thread()` at service layer. Namespace prefix: `kubeai-`
- **WebSocket**: `WS /api/ws?token=<jwt>`. Connection manager (`ws_manager.py`) groups by tenant+user (max 5/user). Redis Pub/Sub (`ws_pubsub.py`) bridges multi-replica broadcast on `kubeai:*` channels
- **Startup** (`core/events.py`): seeds admin (`admin`/`Admin@123456`), delegates to `clients.init_clients()` for shared client init, initializes Casbin, starts WebSocket Pub/Sub and metrics push loop. Idle checker / resource cleaner moved to Taskiq scheduled tasks
- **Taskiq background tasks** (`app/core/taskiq_app.py`): Three process types — FastAPI (API server), Worker (consumes async tasks), Scheduler (fires scheduled tasks). Worker/Scheduler use Redis Streams as broker (DB 1) and result backend (DB 2). Scheduler must be single-replica; Worker can scale. Config: `TASK_MAX_RETRIES` (default 3), `TASK_RETRY_BACKOFF_SECONDS` (default 10)
- **Shared client lifecycle** (`app/core/clients.py`): Lazy-singleton `get_xxx_client()` for Harbor, MinIO, Prometheus, LabelStudio, MLflow. `init_clients()` / `close_clients()` called by both FastAPI `lifespan` and Taskiq `WORKER_STARTUP` / `WORKER_SHUTDOWN` events. **Critical**: Taskiq Worker does NOT run FastAPI lifespan — always import from `app.core.clients`, never from `app.core.events` for client access. `events.py` re-exports getters for backward compatibility only
- **Task modules** (`app/tasks/`): `dev_environment_tasks` (provision + sync_statuses + check_idle), `inference_service_tasks` (deploy + sync_statuses), `resource_cleanup_tasks`. Enqueue from API endpoints via `enqueue_xxx()` helpers that call `.kiq()` on the registered broker task
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

- **Helm** (`infra/helm/kubeai/`): **仅限本地开发部署使用**，包含 12 个组件（PostgreSQL, Redis, MinIO, Volcano, Harbor, kube-prometheus-stack, DCGM exporter, APISIX, backend, frontend, Taskiq worker, Taskiq scheduler）。不要用于生产环境
- **K8s manifests** (`infra/k8s/backend/`): **生产环境专用** — `deployment.yaml` (FastAPI), `worker.yaml` (Taskiq worker: 消费异步任务), `beat.yaml` (Taskiq scheduler: 单副本，触发定时任务)。三者共享 `backend-config` ConfigMap 和 `backend-secret`
- **生产部署位置**: 所有 `infra/k8s/` 下的配置已部署至 **`kubeai-prod-env` 服务器**的 `/root/kubeai` 目录。修改生产配置需通过该服务器操作
- **Images**: Backend/frontend + Jupyter/VS Code/RStudio 开发环境镜像在 `infra/images/`
- **CI/CD**: `.github/workflows/` — `ci.yml` (PR: lint+test), `build.yml` (push to main/dev: GHCR images), `release.yml` (v* tag: versioned images + Helm package)

## Key Conventions

- Backend: Python 3.12+, Ruff (line-length 120, double quotes), mypy strict
- Frontend: pnpm, ESLint 9 flat config, Prettier (no semicolons, single quotes, 100 char width, 2-space indent)
- API: backend snake_case ↔ frontend camelCase (auto-transformed)
- Commits: emoji-prefixed Conventional Commits (`✨ feat:`, `🔧 chore:`, `♻️ refactor:`). See `AGENTS.md`
- K8s: fully async via `kubernetes_asyncio`. Sync external clients (MinIO, Harbor, MLflow) wrapped in `asyncio.to_thread()`
