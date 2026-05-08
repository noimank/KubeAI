# AGENTS.md — KubeAI

## 快速命令

```bash
# 后端 (backend/)
uv sync                    # 安装依赖
uv run pytest              # 全部测试
uv run pytest tests/unit/test_security.py::test_hash_password -v  # 单个测试
uv run uvicorn app.main:app --reload  # 开发服务器 (端口 8000)
uv run ruff check .        # 检查
uv run ruff check --fix .  # 自动修复
uv run ruff format .       # 格式化
uv run mypy app/           # 类型检查

# 前端 (frontend/)
pnpm install               # 安装依赖
pnpm dev                   # 开发服务器 (端口 3000, /api → localhost:8000)
pnpm build                 # 构建 (先 tsc -b 再 vite build)
pnpm lint                  # ESLint
pnpm format                # Prettier
pnpm typecheck             # tsc --noEmit
pnpm test                  # Vitest
pnpm test:watch            # Vitest watch 模式

# 基础设施 (项目根目录)
docker compose -f docker-compose.dev.yml up -d  # PostgreSQL 17 + Redis 7 + MinIO

# 数据库迁移
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "描述"
```

## 那些容易被忽略的事实

- **所有用户可见文本是中文 (zh-CN)** — 没有 i18n 库，字符串硬编码
- **后端 API 返回 `BaseResponse[T]`** 包装：`{success, message, data}`。前端 api.ts 自动在请求时 snake→camel、响应时 camel→snake 转换
- **前端 Token 双重持久化**：localStorage（拦截器读取） + Zustand 状态（React 响应式）
- **`get_db()` 在两处定义**：`app/core/database.py` 和 `app/api/deps.py`，**endpoint 使用 deps.py 中的**
- **多 endpoint 文件已存在但未挂载**：`app/api/endpoints/` 中有 datasets, training_jobs, experiments 等，但只有 `auth`, `credentials`, `tenants` 以及新增的 `datasets`, `images`, `training_jobs`, `users`, `audit_logs` 被挂载。创建新 endpoint 需在 `router.py` 中注册
- **K8s 调用是同步的**：`app/integrations/k8s/` 使用同步 `kubernetes` Python 客户端，会阻塞异步事件循环
- **pre-commit 钩子按顺序执行**：ruff (fix+format) → mypy → eslint → prettier → tsc --noEmit
- **Tailwind preflight 被禁用**：`corePlugins: { preflight: false }` 以兼容 Ant Design
- **暗色模式通过 `[data-theme="dark"]` 属性选择器**，而非 Tailwind 的 `dark:` class
- **Zustand store 间通信**：使用 `useOtherStore.getState()` 模式（如 authStore 在登录时设置 rbacStore role），不使用 middleware
- **后端 `.env` 文件包含实际凭据**（Harbor OIDC 等），生成 .env.example 时需脱敏
- **前端构建分两步**：`tsc -b` 类型检查完成后才 `vite build`（package.json 脚本定义）
- **Vite 配置中 `@` 指向 `src/`**，测试中用 `jsdom` + `setupFiles: ['./tests/setup.ts']`

## 架构速览

```
backend/
  app/
    main.py               # FastAPI 入口
    api/endpoints/router.py # 所有路由在此注册 (prefix=/api)
    core/                 # config, security, casbin, database, redis, exceptions
    models/               # SQLAlchemy (TimestampMixin, SoftDeleteMixin)
    schemas/              # Pydantic (BaseResponse[T])
    services/             # 业务逻辑 (构造函数注入 AsyncSession + 可选 Redis)
    integrations/k8s/     # 同步 K8s 客户端包装
    middleware/           # RequestId, Tenant, ErrorHandler
  tests/                  # pytest (asyncio_mode=auto)
frontend/
  src/
    App.tsx               # 路由定义 (React Router v7, 懒加载)
    services/api.ts       # Axios 实例 (自动 snake/camel 转换 + token 刷新队列)
    stores/               # Zustand (authStore, rbacStore, tenantStore, themeStore)
    components/           # AuthGuard, PermissionGuard
```

## 样式约定

- Python: Ruff (line-length=120, 双引号), mypy strict (pydantic 插件)
- TypeScript/React: Prettier (无分号, 单引号, printWidth=100, 2空格), ESLint 9 flat config
