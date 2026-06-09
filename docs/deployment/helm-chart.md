# Helm 本地调试环境

## 定位

`infra/helm/kubeai/` 只用于本地调试依赖环境，不部署 KubeAI 后端、Taskiq worker/scheduler、前端、应用 Ingress、后端 ConfigMap/Secret 或 RBAC。

本地开发时：

- 后端在本机运行：`uv run uvicorn app.main:app --reload`
- Taskiq worker/scheduler 在本机运行
- 前端在本机运行：`pnpm dev`
- 生产部署由 `infra/k8s/` 负责

## 依赖组件

| 组件 | 默认 | 说明 |
|------|------|------|
| PostgreSQL | 启用 | 主数据库，`values-dev.yaml` 暴露 `30432` |
| Redis | 启用 | 缓存、Taskiq broker/result backend，`values-dev.yaml` 暴露 `30379` |
| MinIO | 启用 | 对象存储，`values-dev.yaml` 暴露 `30900/30901` |
| cert-manager | 开发启用 | KServe webhook TLS 证书依赖 |
| Volcano | 启用 | 训练任务调度依赖 |
| KEDA | 开发启用 | 推理服务自动伸缩联调依赖 |
| KServe | 开发启用 | 本地推理联调基础设施，随 Helm release 安装到 `kubeai` namespace |
| Prometheus/Grafana | 启用 | 本地监控调试，`values-dev.yaml` 暴露 `30090/30030` |
| MLflow | 开发启用 | `values-dev.yaml` 暴露 `30500` |
| Label Studio | 开发启用 | `values-dev.yaml` 暴露 `30800` |
| JupyterHub | 开发启用 | `values-dev.yaml` 暴露 `30801` |
| Harbor | 默认关闭 | 按需启用，资源占用较高 |

本地开发基础设施统一通过 Helm 安装。生产部署仍使用 `infra/k8s/`，其中 KServe 生产 manifests 安装到独立的 `kserve` namespace；本地 Helm 依赖会跟随 release 安装到 `kubeai` namespace。

## 安装

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add volcano-sh https://volcano-sh.github.io/helm-charts
helm repo add kedacore https://kedacore.github.io/charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo add nvidia https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo add harbor https://helm.goharbor.io

helm dependency update infra/helm/kubeai/

helm upgrade --install kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values-dev.yaml \
  -n kubeai --create-namespace
```

## 本地服务配置

后端 `.env` 应连接 Helm 暴露的本地端口：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:30432/kubeai
REDIS_URL=redis://localhost:30379/0
MINIO_ENDPOINT=localhost:30900
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
JUPYTERHUB_API_URL=http://localhost:30801/hub/api
JUPYTERHUB_API_TOKEN=kubeai-dev-jupyterhub-token
JUPYTERHUB_BASE_URL=http://localhost:30801
```

本地需要分别启动：

```bash
cd backend
uv run uvicorn app.main:app --reload
uv run taskiq worker app.core.taskiq_app:broker --fs-discover
uv run taskiq scheduler app.core.taskiq_app:scheduler --skip-first-run

cd ../frontend
pnpm dev
```

## 模板范围

Helm Chart 仅保留依赖服务模板：

| 模板 | 资源 |
|------|------|
| `redis.yaml` | Redis |
| `minio.yaml` | MinIO |
| `mlflow.yaml` | MLflow |
| `labelstudio.yaml` | Label Studio |

其他依赖来自 Helm sub-chart：cert-manager、PostgreSQL、Volcano、KEDA、Prometheus、DCGM Exporter、Harbor、KServe、JupyterHub。
