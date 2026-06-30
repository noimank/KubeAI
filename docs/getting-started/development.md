# 开发环境搭建

## 1. 克隆项目

```bash
git clone https://github.com/noimank/KubeAI.git
cd KubeAI
```

## 2. 启动基础设施服务

使用 Helm 安装开发环境依赖服务：

```bash
# 添加必要的 Helm 仓库
helm repo add jetstack https://charts.jetstack.io
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add volcano-sh https://volcano-sh.github.io/helm-charts
helm repo add kedacore https://kedacore.github.io/charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add nvidia https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo add harbor https://helm.goharbor.io
helm dependency update infra/helm/kubeai/

# 安装本地调试依赖服务
helm upgrade --install kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values-dev.yaml \
  -n kubeai --create-namespace
```

安装完成后，各服务通过 NodePort 暴露：

| 服务 | 地址 |
|------|------|
| PostgreSQL | `localhost:30432` |
| Redis | `localhost:30379` |
| MinIO API | `localhost:30900` |
| MinIO Console | `localhost:30901` |
| MLflow | `localhost:30500` |
| Label Studio | `localhost:30800` |
| APISIX 网关 | Gateway `localhost:30080` / Admin `localhost:30918` |

Helm 还会安装 cert-manager、Volcano、KEDA、KServe 等本地联调基础设施。Helm 不部署后端、Taskiq worker/scheduler 和前端，这三个进程都在本机启动。

## 3. 后端开发环境

```bash
cd backend/

# 复制环境变量文件
cp .env.example .env
# 编辑 .env 文件，配置数据库、Redis、MinIO 等连接信息
```

`.env` 关键配置项：

```bash
# 数据库（使用开发环境的 NodePort）
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:30432/kubeai

# Redis
REDIS_URL=redis://localhost:30379/0

# MinIO
MINIO_ENDPOINT=localhost:30900
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# JWT 密钥（开发环境可使用默认值）
SECRET_KEY=your-secret-key-here

# Label Studio
LABEL_STUDIO_URL=http://localhost:30800
LABEL_STUDIO_API_TOKEN=your-token

# MLflow
MLFLOW_TRACKING_URI=http://localhost:30500

# Harbor（开发环境可选）
HARBOR_URL=http://harbor.kubeai.local

# APISIX（原生 Pod 开发环境动态路由）
KUBEAI_APISIX_ADMIN_URL=http://localhost:30918
KUBEAI_APISIX_ADMIN_KEY=edd1c9f034335f136f87ad84b625c8f1
KUBEAI_BACKEND_INTERNAL_URL=http://localhost:8000
```

安装依赖并启动：

```bash
# 安装 Python 依赖
uv sync

# 运行数据库迁移
uv run alembic upgrade head

# 启动开发服务器（端口 8000）
uv run uvicorn app.main:app --reload

# 另开终端启动后台任务 worker
uv run taskiq worker app.core.taskiq_app:broker --fs-discover

# 另开终端启动定时任务 scheduler
uv run taskiq scheduler app.core.taskiq_app:scheduler --skip-first-run
```

验证后端启动成功：

```bash
curl http://localhost:8000/api/health
# 返回 {"success": true, "message": "ok", "data": null}
```

## 4. 前端开发环境

```bash
cd frontend/

# 安装 Node.js 依赖
pnpm install

# 启动开发服务器（端口 3000，自动代理 /api 到 localhost:8000）
pnpm dev
```

验证前端启动成功：访问 http://localhost:3000

## 5. 初始管理员账号

系统首次启动时会自动创建默认管理员账号：

| 字段 | 值 |
|------|------|
| 用户名 | `admin` |
| 密码 | `Admin@123456` |
| 角色 | `admin` |
| 租户 | 默认租户 |

!!! warning "注意"
    生产环境请务必修改默认管理员密码。

## 6. 常用开发命令

### 后端

```bash
# 运行测试
uv run pytest                              # 全部测试
uv run pytest tests/unit/                  # 仅单元测试
uv run pytest tests/integration/           # 仅集成测试
uv run pytest tests/unit/test_security.py  # 单个测试文件
uv run pytest -k "test_hash_password"      # 按名称匹配

# 代码检查
uv run ruff check .                        # Lint
uv run ruff check --fix .                  # 自动修复
uv run ruff format .                       # 格式化
uv run mypy app/                           # 类型检查

# 数据库迁移
uv run alembic upgrade head                # 应用所有迁移
uv run alembic revision --autogenerate -m "description"  # 生成迁移
```

### 前端

```bash
pnpm dev          # 启动开发服务器
pnpm build        # 构建生产版本
pnpm lint         # ESLint 检查
pnpm format       # Prettier 格式化
pnpm typecheck    # TypeScript 类型检查
pnpm test         # 运行测试
pnpm test:watch   # 监听模式运行测试
```
