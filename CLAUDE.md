# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KubeAI is a Kubernetes-native AI/ML platform with multi-tenant RBAC. Monorepo with FastAPI backend (`backend/`) and React frontend (`frontend/`). Deployed via Helm chart (`infra/helm/kubeai/`). All user-facing text is in Chinese (zh-CN) — no i18n library, strings are hardcoded.

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

# Build (tsc -b then vite build)
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
# Deploy all services via Helm (PostgreSQL, Redis, MinIO, Volcano, Harbor, backend, frontend)
helm install kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values-dev.yaml \
  -n kubeai --create-namespace

# Docker build (from project root)
docker build -t kubeai-backend -f infra/images/backend/Dockerfile .
docker build -t kubeai-frontend -f infra/images/frontend/Dockerfile .
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
- **Services**: Constructor-injected with `AsyncSession` (and optionally Redis/MinIO). Key services:
  - `AuthService` — register/login/lockout/refresh/logout
  - `TenantService` — K8s namespace + ResourceQuota + NetworkPolicy with rollback on failure
  - `CredentialService` — async K8s Secret management (no DB)
  - `OAuthService` — OIDC/OAuth2 via authlib with Redis-cached discovery docs
  - `DatasetService` — MinIO-backed dataset/version management with presigned URLs
  - `ImageService` — custom image builds via K8s Jobs, push to Harbor registry
  - `TrainingJobService` — creates Volcano VCJobs, manages PVCs for dataset mounts, tracks quota
  - `ExperimentService` — MLflow-backed experiment tracking, reproduces experiments as training jobs
  - `InvitationService` — tenant member invitation with role assignment
  - `AuditService` — records audit logs for resource operations
  - `AnnotationService` — Label Studio-backed annotation projects with custom XML config, task assignment, and annotation writeback to dataset versions
  - `DevEnvironmentService` — JupyterHub-based dev environments with dataset mounting, idle timeout auto-stop, and training job creation from notebooks
  - `InferenceService` — KServe-based model inference with KEDA autoscaling, canary deployments, and API token auth
- **Model registry**: No dedicated service — `app/api/endpoints/model_registry.py` handles logic directly. Models in `app/models/registered_model.py` (`RegisteredModel` + `ModelVersion`). Versions uploaded via K8s upload Jobs, files stored in MinIO
- **Multi-tenancy**: Three layers — DB-level (`TenantMixin` + FK), app-level (`TenantMiddleware` + `require_tenant_access`), infra-level (K8s NetworkPolicy per namespace isolating tenant traffic)
- **External integrations** (`app/integrations/`):
  - `k8s/` — async `kubernetes_asyncio` client (CoreV1Api, NetworkingV1Api, BatchV1Api). Handles namespace, PVC, Secret, Job, ResourceQuota, NetworkPolicy, upload Jobs. Client lifecycle managed via `get_k8s_clients()` / `close_k8s_clients()`. Pure construction helpers (e.g. `create_build_job`, `build_tenant_resource_quota`) remain sync
  - `mlflow/` — MLflow REST API client via `httpx` for experiment/run tracking. Sync calls wrapped in `asyncio.to_thread()` at service level
  - `volcano/` — Volcano batch scheduler via async K8s CustomObjectsApi (`batch.volcano.sh/v1alpha1` VCJobs). Maps Volcano phases to internal status (Pending→pending, Running→running, Completed→succeeded, etc.)
  - `harbor/` — Harbor REST API client via `httpx` for container registry management (projects, repos, robots). Sync calls wrapped in `asyncio.to_thread()` at service level
  - `minio/` — MinIO/S3 client for dataset file storage (buckets, presigned upload/download URLs). Sync calls wrapped in `asyncio.to_thread()` at service level
  - `jupyterhub/` — JupyterHub REST API client via `httpx` for dev environment lifecycle (user creation, server start/stop, spawner management)
  - `labelstudio/` — Label Studio REST API client + XML template builder (`templates.py`) for annotation projects. Supports image classification, object detection, segmentation, text classification, and custom choices/text areas
  - `kserve/` — KServe inference services via async K8s CustomObjectsApi (`serving.kserve.io/v1beta1`). Builder pattern for InferenceService specs, canary rollout support
  - `keda/` — KEDA autoscaler via async K8s CustomObjectsApi (`keda.sh/v1alpha1`). Builds ScaledObjects for inference service auto-scaling
  - Namespace prefix: `kubeai-`
- **API responses**: All endpoints return `BaseResponse[T]` wrapper (`{success, message, data}`)
- **Exceptions**: `AppException` hierarchy in `app/core/exceptions.py` — caught by error handler middleware returning `BaseResponse` with appropriate HTTP status. All default messages are in Chinese
- **Startup**: `app/core/events.py` — initializes Redis, Casbin, seeds admin user (`admin`/`Admin123456`) and default tenant, creates MinIO client singleton (accessed via `get_minio_client()`)
- **Tests**: `asyncio_mode = "auto"` in pytest config. `conftest.py` provides session-scoped `event_loop` + `httpx.AsyncClient` with `ASGITransport` for in-process testing. Unit tests in `tests/unit/`, integration in `tests/integration/`
- **Mounted routers** (`api/endpoints/router.py`): auth, annotations, audit_logs, credentials, datasets, dev_environments, experiments, images, inference_services, inference_proxy, model_registry, tenants, training_jobs, users

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

### Infrastructure (`infra/`)

- **Helm chart**: `infra/helm/kubeai/` — deploys PostgreSQL 17, Redis 7, MinIO, Volcano scheduler, Harbor registry, backend, and frontend. Dependencies managed via Chart.lock
- **Docker images**: `infra/images/backend/Dockerfile`, `infra/images/frontend/Dockerfile`
- **CI/CD**: `.github/workflows/` — `ci.yml` runs backend lint+test, frontend lint+test, and helm lint on PRs to main/dev

### Key Conventions

- Backend API uses snake_case; frontend auto-transforms to camelCase
- All API responses wrapped in `BaseResponse` (`{success, message, data}`)
- Backend: Python 3.12+, Ruff (line-length 120, double quotes), mypy strict with pydantic plugin
- Frontend: pnpm, ESLint 9 flat config, Prettier (no semicolons, single quotes, 100 char width, 2-space indent), Vitest
- `get_db()` exists in both `app/core/database.py` and `app/api/deps.py` — endpoints must use the one from `deps.py`
- K8s calls are fully async via `kubernetes_asyncio` — all integration functions return coroutines and must be `await`ed
- MinIO and Harbor clients are synchronous — wrap their calls in `asyncio.to_thread()` at the service layer
