# KubeAI 独立部署 YAML

按需部署 KubeAI 平台的各个组件，替代 Helm 一键部署方式。每个组件独立维护，可单独部署。

## 目录结构

```
infra/k8s/
├── namespace.yaml              # 命名空间 (必须首先部署)
├── backend-config.yaml         # 后端 ConfigMap + Secret (所有配置项，按需修改)
├── backend-rbac.yaml           # 后端集群权限 (ServiceAccount/ClusterRole)
│
├── postgresql/                 # PostgreSQL 数据库
│   └── postgresql.yaml         #   含 mlflow/labelstudio 数据库初始化
├── redis/                      # Redis 缓存
│   └── redis.yaml
├── minio/                      # MinIO 对象存储
│   └── minio.yaml
├── backend/                    # FastAPI 后端
│   ├── deployment.yaml         #   含数据库迁移 initContainer
│   └── service.yaml
├── frontend/                   # React 前端
│   ├── deployment.yaml
│   └── service.yaml
├── mlflow/                     # MLflow 实验追踪 (可选)
│   └── mlflow.yaml
├── labelstudio/                # Label Studio 数据标注 (可选)
│   └── labelstudio.yaml
├── ingress/                    # 前端 Ingress (可选)
│   └── ingress.yaml
│
├── volcano/                    # Volcano 批处理调度器
│   ├── volcano.yaml            #   helm template 渲染，可直接 kubectl apply
│   └── README.md
├── jupyterhub/                 # JupyterHub 开发环境
│   ├── jupyterhub.yaml         #   含 KubeAI 自定义 Authenticator + Spawner
│   └── README.md
├── harbor/                     # Harbor 镜像仓库
│   ├── harbor.yaml             #   helm template 渲染
│   └── README.md
├── prometheus/                 # Prometheus + Grafana 监控
│   ├── prometheus.yaml         #   helm template 渲染
│   └── README.md
├── dcgm-exporter/              # NVIDIA GPU 指标采集
│   ├── dcgm-exporter.yaml      #   helm template 渲染
│   └── README.md
├── kserve/                     # KServe 模型推理服务
│   ├── kserve-crd.yaml        #   CRDs (helm template 渲染)
│   ├── kserve.yaml            #   Controller + Webhooks
│   └── README.md
└── keda/                       # KEDA 自动扩缩容
    ├── keda.yaml              #   helm template 渲染
    └── README.md
```

## 组件依赖关系

```
namespace.yaml
  │
  ├── 基础设施
  │   ├── postgresql/        ← mlflow/labelstudio 依赖此数据库
  │   ├── redis/             ← backend 依赖
  │   └── minio/             ← backend 依赖
  │
  ├── 应用层
  │   ├── backend/           ← 依赖基础设施 + ConfigMap/Secret/RBAC
  │   └── frontend/          ← 依赖 backend
  │
  ├── 可选应用
  │   ├── mlflow/            ← 依赖 postgresql (mlflow 库)
  │   ├── labelstudio/       ← 依赖 postgresql (labelstudio 库)
  │   └── ingress/           ← 依赖 frontend + Ingress Controller
  │
  └── 平台组件
      ├── volcano/           ← backend 训练任务调度
      ├── jupyterhub/        ← 交互式开发环境
      ├── harbor/            ← 自定义镜像构建
      ├── prometheus/        ← 监控指标采集
      ├── dcgm-exporter/     ← GPU 指标 (需 GPU 节点)
      ├── kserve/            ← backend 推理服务管理
      └── keda/              ← 推理服务自动扩缩容
```

## 快速部署

### 1. 最小化部署 (本地开发)

适合前后端在集群外运行，仅部署基础设施：

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/postgresql/
kubectl apply -f infra/k8s/redis/
kubectl apply -f infra/k8s/minio/

# 等待 PostgreSQL 就绪
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql -n kubeai --timeout=120s

# 本地启动后端
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

### 2. 完整集群内部署

```bash
# 1. 命名空间
kubectl apply -f infra/k8s/namespace.yaml

# 2. 基础设施
kubectl apply -f infra/k8s/postgresql/
kubectl apply -f infra/k8s/redis/
kubectl apply -f infra/k8s/minio/

# 3. 等待 PostgreSQL 就绪
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql -n kubeai --timeout=120s

# 4. 后端配置 (部署前修改 Secret 中的 SECRET_KEY 和密码)
kubectl apply -f infra/k8s/backend-config.yaml
kubectl apply -f infra/k8s/backend-rbac.yaml

# 5. 后端 + 前端
kubectl apply -f infra/k8s/backend/
kubectl apply -f infra/k8s/frontend/

# 6. 可选应用
kubectl apply -f infra/k8s/mlflow/          # 实验追踪
kubectl apply -f infra/k8s/labelstudio/     # 数据标注

# 7. 平台组件 (按需部署)
kubectl apply -f infra/k8s/volcano/volcano.yaml       # 训练任务调度
kubectl apply -f infra/k8s/jupyterhub/jupyterhub.yaml # 开发环境
kubectl apply -f infra/k8s/harbor/harbor.yaml         # 镜像仓库
kubectl apply -f infra/k8s/prometheus/prometheus.yaml # 监控
kubectl apply -f infra/k8s/kserve/kserve-crd.yaml     # KServe CRDs (先装)
kubectl apply -f infra/k8s/kserve/kserve.yaml         # KServe Controller
kubectl apply -f infra/k8s/keda/keda.yaml             # 自动扩缩容
```

## 端口映射 (本地访问)

```bash
kubectl port-forward -n kubeai svc/postgresql 5432:5432
kubectl port-forward -n kubeai svc/backend 8000:8000
kubectl port-forward -n kubeai svc/frontend 3000:80
kubectl port-forward -n kubeai svc/minio 9001:9001
kubectl port-forward -n kubeai svc/mlflow 5000:5000
kubectl port-forward -n kubeai svc/labelstudio 8080:8080
```

NodePort 已配置，可直接通过节点 IP 访问：

| 组件          | NodePort | 说明 |
|--------------|----------|------|
| PostgreSQL   | 30432    | 数据库 |
| Redis        | 30379    | 缓存 |
| MinIO API    | 30900    | 对象存储 API |
| MinIO 控制台  | 30901    | MinIO Web UI |
| MLflow       | 30500    | 实验追踪 UI |
| Label Studio | 30800    | 标注 UI |
| JupyterHub   | 30801    | 开发环境 |
| Prometheus   | 30090    | 监控 |
| Grafana      | 30030    | 仪表盘 |

## 配置说明

`backend-config.yaml` 包含 ConfigMap + Secret，所有字段与 `backend/app/core/config.py` 对齐。

**必须修改 (Secret):**

1. **SECRET_KEY** — JWT 签名密钥: `openssl rand -hex 32`
2. **DATABASE_URL** — 密码需与 `postgresql/postgresql.yaml` 中的 `POSTGRES_PASSWORD` 一致
3. **MINIO_ACCESS_KEY / MINIO_SECRET_KEY** — 需与 `minio/minio.yaml` 中的 `MINIO_ROOT_USER/PASSWORD` 一致

**按启用组件修改 (ConfigMap):**

| 组件 | 启用方式 |
|-----|---------|
| MLflow | `MLFLOW_ENABLED: "true"` + `MLFLOW_TRACKING_URI` 指向 MLflow Service |
| Label Studio | `LABEL_STUDIO_URL` 指向 Label Studio Service + Secret 中配置 `LABEL_STUDIO_API_TOKEN` |
| JupyterHub | ConfigMap 中 `JUPYTERHUB_API_URL` / `JUPYTERHUB_BASE_URL` + Secret 中配置 `JUPYTERHUB_API_TOKEN` |
| OIDC/SSO | `OIDC_ENABLED: "true"` + Secret 中配置 `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` |
| Harbor | Secret 中配置 `HARBOR_URL` / `HARBOR_PASSWORD` |

## 清理

```bash
# 可选应用
kubectl delete -f infra/k8s/ingress/
kubectl delete -f infra/k8s/labelstudio/
kubectl delete -f infra/k8s/mlflow/

# 应用层
kubectl delete -f infra/k8s/frontend/
kubectl delete -f infra/k8s/backend/

# 平台组件
kubectl delete -f infra/k8s/keda/keda.yaml
kubectl delete -f infra/k8s/kserve/kserve.yaml
kubectl delete -f infra/k8s/kserve/kserve-crd.yaml
kubectl delete -f infra/k8s/volcano/volcano.yaml
kubectl delete -f infra/k8s/jupyterhub/jupyterhub.yaml
kubectl delete -f infra/k8s/harbor/harbor.yaml
kubectl delete -f infra/k8s/dcgm-exporter/dcgm-exporter.yaml
kubectl delete -f infra/k8s/prometheus/prometheus.yaml

# 配置 + 基础设施 + 命名空间
kubectl delete -f infra/k8s/backend-rbac.yaml
kubectl delete -f infra/k8s/backend-config.yaml
kubectl delete -f infra/k8s/minio/
kubectl delete -f infra/k8s/redis/
kubectl delete -f infra/k8s/postgresql/
kubectl delete -f infra/k8s/namespace.yaml
```
