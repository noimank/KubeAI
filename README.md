# KubeAI

Kubernetes-native AI/ML 平台。

## 环境要求

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python 包管理)
- pnpm (`corepack enable && corepack prepare pnpm@latest --activate`)
- Kubernetes 集群 (kind / minikube / Docker Desktop 等)
- Helm 3.8+

## 快速开始

### 1. Helm 部署本地调试依赖

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add volcano-sh https://volcano-sh.github.io/helm-charts
helm repo add kedacore https://kedacore.github.io/charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add nvidia https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo add harbor https://helm.goharbor.io
helm dependency update infra/helm/kubeai/

helm upgrade --install kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values-dev.yaml \
  -n kubeai --create-namespace
```

Helm 只部署本地调试基础设施，例如 cert-manager、PostgreSQL、Redis、MinIO、Volcano、KEDA、KServe、Prometheus、MLflow、Label Studio、APISIX。后端 API、Taskiq worker/scheduler 和前端不通过 Helm/K8s 部署。

### 2. 本地开发

先确保集群中已部署基础依赖服务，然后：

```bash
# 后端
cd backend
cp .env.example .env          # 修改数据库/Redis/MinIO 连接地址
uv sync                       # 安装依赖
uv run alembic upgrade head   # 数据库迁移
uv run uvicorn app.main:app --reload   # 启动 http://localhost:8000
uv run taskiq worker app.core.taskiq_app:broker --fs-discover
uv run taskiq scheduler app.core.taskiq_app:scheduler --skip-first-run

# 前端
cd frontend
pnpm install                  # 安装依赖
pnpm dev                      # 启动 http://localhost:3000，自动代理 /api → localhost:8000
```

### 默认账号

启动后自动创建管理员：`admin` / `Admin@123456`

## 基础设施组件说明

| 组件 | 用途 | 安装方式 |
|------|------|---------|
| cert-manager | KServe webhook TLS 证书 | 本地 Helm / 生产 `infra/k8s` 前置 |
| Volcano | 训练任务调度 (VCJob) | 本地 Helm / 生产 `infra/k8s/volcano/` |
| KEDA | 推理服务自动伸缩 | 本地 Helm / 生产 `infra/k8s/keda/` |
| KServe | 模型推理服务 | 本地 Helm / 生产 `infra/k8s/kserve/` |

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

## 容器镜像构建

```bash
docker build -t kubeai-backend -f infra/images/backend/Dockerfile .
docker build -t kubeai-frontend -f infra/images/frontend/Dockerfile .
```
