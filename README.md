# KubeAI

Kubernetes-native AI/ML 平台。

## 环境要求

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python 包管理)
- pnpm (`corepack enable && corepack prepare pnpm@latest --activate`)
- Docker + K8s 集群 (kind / minikube)
- Helm 3

## 快速开始

### 1. 启动基础服务 + 平台

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add volcano-sh https://volcano-sh.github.io/helm-charts
helm dependency update infra/helm/kubeai/

helm install kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values-dev.yaml \
  -n kubeai --create-namespace
```

一键部署 PostgreSQL、Redis、MinIO、Volcano 调度器、后端、前端。

### 2. 本地开发（仅后端/前端热更新）

先确保集群中已部署基础服务（PostgreSQL、Redis、MinIO），然后：

```bash
# 后端
cd backend
cp .env.example .env          # 修改数据库/Redis/MinIO 连接地址
uv sync                       # 安装依赖
uv run alembic upgrade head   # 数据库迁移
uv run uvicorn app.main:app --reload   # 启动 http://localhost:8000

# 前端
cd frontend
pnpm install                  # 安装依赖
pnpm dev                      # 启动 http://localhost:3000，自动代理 /api → localhost:8000
```

### 默认账号

启动后自动创建管理员：`admin` / `Admin123456`

## 常用命令

```bash
# 后端
cd backend
uv run pytest                          # 跑测试
uv run ruff check . && ruff format .   # 代码格式化
uv run mypy app/                       # 类型检查

# 前端
cd frontend
pnpm lint       # ESLint
pnpm typecheck  # TypeScript 检查
pnpm test       # Vitest
```

## Docker 构建

```bash
docker build -t kubeai-backend -f infra/images/backend/Dockerfile .
docker build -t kubeai-frontend -f infra/images/frontend/Dockerfile .
```
