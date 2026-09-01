## Project Overview

KubeAI is a Kubernetes-native AI/ML platform with multi-tenant RBAC. Monorepo: FastAPI backend (`backend/`) + React frontend (`frontend/`). All user-facing text is hardcoded zh-CN — no i18n.

**部署**: Helm chart (`infra/helm/kubeai/`) 仅本地开发（一键部署完整依赖链：PostgreSQL, Redis, MinIO, Volcano, Harbor, APISIX, Prometheus stack）。生产用 `infra/k8s/` manifests，已部署在 `kubeai-prod-env` 服务器的 `/root/kubeai`。

## Development Commands

### Backend (from `backend/`)

```bash
uv sync
uv run uvicorn app.main:app --reload                                                 # API (port 8000)
uv run taskiq worker app.core.taskiq_app:broker --fs-discover                         # 异步任务 (开发环境/推理等须并行运行)
uv run taskiq scheduler app.core.taskiq_app:scheduler --skip-first-run                # 定时任务
uv run pytest tests/unit/test_security.py::test_hash_password -v                      # 单个测试
uv run alembic revision --autogenerate -m "desc" && uv run alembic upgrade head       # 生成+迁移
uv run ruff check . && uv run ruff format . && uv run mypy app/                       # lint+format+type
```

### Frontend (from `frontend/`)

```bash
pnpm install && pnpm dev          # port 3000, proxies /api → :8000
pnpm build && pnpm lint && pnpm typecheck && pnpm test
```

### Infra & Docs (from project root)

```bash
helm install kubeai infra/helm/kubeai/ -f infra/helm/kubeai/values-dev.yaml -n kubeai --create-namespace
docker build -t kubeai-backend -f infra/images/backend/Dockerfile .
uv sync --group docs && uv run mkdocs serve --config-file ../mkdocs.yml   # run from backend/
```

Pre-commit (`.pre-commit-config.yaml`): ruff+mypy backend, eslint+prettier+tsc frontend — `pre-commit install`.

## Architecture

### Backend (`backend/app/`)

- **Entry**: `main.py` — FastAPI + lifespan, middleware stack (RequestId → Tenant → error handlers), routers under `/api`
- **Config**: `core/config.py` (Pydantic Settings, `.env`). **DB**: async SQLAlchemy 2.0 (`Mapped`/`mapped_column`); models use `TimestampMixin`, User adds `SoftDeleteMixin`; migrations in `alembic/` (asyncpg)
- **Auth**: JWT HS256 (`core/security.py`), Redis token blacklist, 5-failure lockout (15min TTL). **Identity resolution** unified in `core/identity.py` `IdentityResolver` — decode → blacklist → Redis-cached `TokenIdentity` (`user_token_version`/`tenant_status` enable active invalidation on disable). Shared by FastAPI deps / WebSocket / APISIX forward-auth. Browser-native requests (WS/SSE/downloads) authenticate via same-origin Cookie `kubeai_access_token` (SameSite=Lax + `Sec-Fetch-Site` check, Bearer header still takes priority — `deps.HeaderOrCookieUser`); JWT never travels in URLs. Production (`DEBUG=false`) refuses to boot on a public default `SECRET_KEY` (fail-fast in `core/config.py`)
- **RBAC**: Casbin (`core/casbin.py`, `rbac_model.conf`). Roles admin>mlops>engineer>annotator; `manage` action is wildcard. Policies seeded from `permissions.py`; permissions are `resource:action` strings
- **DI** (`api/deps.py`): `CurrentUser` (`TokenIdentity`), `CurrentUserEntity` (full ORM, profile/password writes only), `require_permission`, `require_tenant_access`. **Critical**: `get_db()` exists in both `core/database.py` and `api/deps.py` — endpoints MUST use `deps.py`
- **Pattern**: responses wrapped in `BaseResponse[T]` (`{success,message,data}`); `AppException` hierarchy (`core/exceptions.py`) caught by middleware
- **Services** (`services/`): constructor-injected `AsyncSession` (+ optional Redis), one per domain (auth, tenants, datasets, training via Volcano VCJobs, inference, experiments via MLflow, annotations + annotation templates via Label Studio, dev environments + dev env images, images via Harbor, algorithms, hyperparameter tuning via Optuna — sampler/stopping config + pause-resume, business configs (platform branding), data exploration via db_connections + query_results (read-only SQL whitelist; PG enforces server-side read-only transaction), credentials, notifications, restricted filesystem browsing (仅当前用户 home + 租户 workspace, 其它路径 403), monitoring, dashboard, audit, quota, OAuth, invitations). Model registry has no service — logic lives in its endpoint module
- **Multi-tenancy**: DB (`TenantMixin`+FK) → app (`TenantMiddleware`+`require_tenant_access`) → infra (NetworkPolicy per namespace). Namespace prefix `kubeai-`
- **Integrations** (`integrations/`): `k8s/` (async kubernetes_asyncio), `volcano/`, `keda/`, `harbor/`, `minio/`, `mlflow/`, `labelstudio/`, `prometheus/` (DCGM GPU), `storage/` (local filesystem). K8s fully async; MinIO/Harbor/MLflow sync → wrap in `asyncio.to_thread()`
- **Storage & volumes**: models/datasets on local filesystem. `ModelStorage` (`integrations/storage/model_storage.py`) lays out `{MODEL_BASE_PATH}/{tenant}/{storage_path}`. Pods consume these via hostPath volumes (`integrations/k8s/kubeai_volumes.py`: home/workspace/models under `/kubeai/*` and `/data/kubeai/models/<tenant>`). Inference Pods read model weights directly from the hostPath mount — **no model-pull initContainer**
- **Shared clients** (`core/clients.py`): lazy-singleton `get_xxx_client()` for Harbor/MinIO/Prometheus/LabelStudio/MLflow; `init_clients()`/`close_clients()` run in both FastAPI lifespan and Taskiq `WORKER_STARTUP`/`WORKER_SHUTDOWN`. **Critical**: Worker does NOT run FastAPI lifespan — always import from `core/clients.py`, never `core/events.py` (it only re-exports for compat)
- **Taskiq** (`core/taskiq_app.py`): 3 process types — API / Worker (async tasks) / Scheduler (定时, single-replica). Redis Streams broker (DB1) + result backend (DB2). Task modules in `tasks/`; enqueue from endpoints via `enqueue_xxx()` helpers calling `.kiq()`
- **WebSocket**: `WS /api/ws` — 握手鉴权用同源 Cookie (`deps.authenticate_ws`), token 不经 URL。Manager groups by tenant+user (max 5/user); Redis Pub/Sub (`ws_pubsub.py`) bridges multi-replica broadcast on `kubeai:*` channels
- **Startup** (`core/events.py`): seeds admin (`admin`/`Admin@123456`), runs `clients.init_clients()`, Casbin init, WS Pub/Sub + metrics push. Idle checker / resource cleaner are Taskiq scheduled tasks
- **Tests**: `asyncio_mode=auto`; `conftest.py` provides `httpx.AsyncClient`+`ASGITransport`. Unit in `tests/unit/`, integration in `tests/integration/`

### Frontend (`frontend/`)

React 18 + TS strict + Ant Design 5 + ProComponents + Zustand + TanStack Query + Tailwind (preflight disabled). Vite 6, `@`→`src/`. React Router v7 (lazy-loaded): `AuthGuard`→`MainLayout`(ProLayout)→`PermissionGuard`. 5 Zustand stores (`auth`,`rbac`,`tenant`,`notification`,`ws`); cross-store via `useOtherStore.getState()`. WebSocket reconnect w/ exp backoff; events invalidate React Query caches by domain (training, inference, dev_environment, cluster_resource). API client (`services/api.ts`): Axios w/ recursive snake_case↔camelCase transform; concurrent 401 refresh queued. RBAC strings `resource:action`, admin=`*`; sidebar filtered via `filterMenuItems()`. Tests: Vitest+jsdom mirroring `src/` under `tests/`.

### Infrastructure (`infra/`)

- **Helm** (`helm/kubeai/`): dev-only, full dependency stack — **不要用于生产**
- **K8s manifests** (`k8s/`): prod — `backend/` (`deployment`=FastAPI / `worker`=Taskiq worker / `beat`=scheduler, sharing `backend-config` ConfigMap + `backend-secret`), plus `volcano/`, `keda/`. All deployed on `kubeai-prod-env`:`/root/kubeai` — 改生产配置需经该服务器
- **Images** (`images/`): backend/frontend + Jupyter/VS Code/RStudio dev env images
- **CI/CD** (`.github/workflows/`): `ci.yml` (PR lint+test), `build.yml` (push main/dev→GHCR), `release.yml` (v* tag→versioned images + Helm)

## Key Conventions

- Backend: Python 3.12+, Ruff (line-length 120, double quotes), mypy strict
- Frontend: pnpm, ESLint 9 flat, Prettier (no semicolons, single quotes, 100 width, 2-space)
- API: backend snake_case ↔ frontend camelCase (auto-transformed)
- Commits: emoji-prefixed Conventional Commits (`✨ feat:`, `🔒 fix:`, `♻️ refactor:`, `✅ test:`). See `AGENTS.md`
- K8s: fully async via `kubernetes_asyncio`; sync external clients (MinIO, Harbor, MLflow) wrapped in `asyncio.to_thread()`
- 平台品牌名/Logo 由后端下发（登录响应 + `frontend/public/logo.jpg`），前端不硬编码；第三方登录账号的资料与凭证由身份提供方统一管理，禁止本地修改
- 杂项目录：`_bmad/`+`_bmad-output/` = BMAD 规划产物；`examples/` = 示例训练项目；`site/` = mkdocs 构建产物（勿手改）
