# KubeAI 独立部署 YAML

按需部署 KubeAI 平台的各个组件，替代 Helm 一键部署方式。每个组件独立维护，可单独部署。

## 目录结构

```
infra/k8s/
├── namespace.yaml               # 命名空间 (必须首先部署)
├── backend-config.yaml          # 后端 ConfigMap + Secret (所有配置项，按需修改)
├── backend-rbac.yaml            # 后端集群权限 (ServiceAccount/ClusterRole/ClusterRoleBinding)
│
├── postgresql/                  # PostgreSQL 数据库
│   └── postgresql.yaml          #   含 mlflow/labelstudio 数据库初始化
├── redis/                       # Redis 缓存
│   └── redis.yaml
├── minio/                       # MinIO 对象存储
│   └── minio.yaml
├── backend/                     # FastAPI 后端
│   ├── deployment.yaml          #   含数据库迁移 initContainer + 健康检查
│   └── service.yaml
├── frontend/                    # React 前端 (Nginx 反向代理 /api → backend)
│   ├── deployment.yaml
│   └── service.yaml
├── mlflow/                      # MLflow 实验追踪 (可选)
│   └── mlflow.yaml
├── labelstudio/                 # Label Studio 数据标注 (可选)
│   └── labelstudio.yaml
├── ingress/                     # Ingress 入口 (可选)
│   └── ingress.yaml             #   仅路由到 frontend，nginx 内部代理 /api 和 /ws
│
├── volcano/                     # Volcano 批处理调度器
│   ├── volcano.yaml             #   helm template 渲染，可直接 kubectl apply
│   └── README.md
├── jupyterhub/                  # JupyterHub 开发环境
│   ├── jupyterhub.yaml          #   含 KubeAI 自定义 Authenticator + Spawner
│   └── README.md
├── harbor/                      # Harbor 镜像仓库
│   ├── harbor.yaml              #   helm template 渲染
│   └── README.md
├── prometheus/                  # Prometheus + Grafana 监控
│   ├── prometheus.yaml          #   helm template 渲染
│   └── README.md
├── dcgm-exporter/               # NVIDIA GPU 指标采集
│   ├── dcgm-exporter.yaml       #   helm template 渲染
│   └── README.md
├── kserve/                      # KServe 模型推理服务
│   ├── kserve-crd.yaml          #   CRDs (helm template 渲染，必须先安装)
│   ├── kserve.yaml              #   Controller + Webhooks
│   └── README.md
└── keda/                        # KEDA 自动扩缩容
    ├── keda.yaml                #   helm template 渲染
    └── README.md
```

## 部署前检查清单

部署前请确认以下事项：

| 检查项 | 说明 |
|-------|------|
| Kubernetes 集群 | 可正常连接，`kubectl cluster-info` 通过 |
| 集群权限 | 需要 ClusterAdmin 权限（创建 ClusterRole、ClusterRoleBinding） |
| 镜像就绪 | `kubeai-backend:0.1.0` 和 `kubeai-frontend:0.1.0` 已 build 或可拉取 |
| SECRET_KEY | `backend-config.yaml` 中已替换为随机密钥 (`openssl rand -hex 32`) |
| 数据库密码 | Secret 中 `DATABASE_URL` 密码与 `postgresql/postgresql.yaml` 一致 |
| MinIO 凭证 | Secret 中 `MINIO_ACCESS_KEY/SECRET_KEY` 与 `minio/minio.yaml` 一致 |

## 快速部署

#### 1. 最小化部署 (本地开发)

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

#### 2. 完整集群内部署

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
kubectl apply -f infra/k8s/kserve/kserve-crd.yaml      # KServe CRDs (先装)
kubectl apply -f infra/k8s/kserve/kserve.yaml          # KServe Controller
kubectl apply -f infra/k8s/keda/keda.yaml              # 自动扩缩容
kubectl apply -f infra/k8s/jupyterhub/jupyterhub.yaml  # 开发环境
kubectl apply -f infra/k8s/harbor/harbor.yaml          # 镜像仓库
kubectl apply -f infra/k8s/prometheus/prometheus.yaml  # 监控
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
  │   └── frontend/          ← 依赖 backend (nginx 代理 /api → backend:8000)
  │
  ├── 可选应用
  │   ├── mlflow/            ← 依赖 postgresql (mlflow 库)
  │   ├── labelstudio/       ← 依赖 postgresql (labelstudio 库)
  │   └── ingress/           ← 依赖 frontend + Ingress Controller
  │
  └── 平台组件
      ├── volcano/           ← backend 训练任务调度 (需要 RBAC 权限)
      ├── kserve/            ← backend 推理服务管理 (需要 RBAC 权限)
      │   ├── kserve-crd.yaml   (CRDs，必须先安装)
      │   └── kserve.yaml       (Controller + Webhooks)
      ├── keda/              ← 推理服务自动扩缩容 (需要 RBAC 权限)
      ├── jupyterhub/        ← 交互式开发环境
      ├── harbor/            ← 自定义镜像构建
      ├── prometheus/        ← 监控指标采集
      └── dcgm-exporter/     ← GPU 指标 (需 GPU 节点)
```

## RBAC 权限说明

`backend-rbac.yaml` 创建了 `kubeai-backend` ClusterRole，包含以下权限：

| API Group | 资源 | 操作 | 用途 |
|-----------|------|------|------|
| `""` (core) | namespaces | get, list, create, delete, watch | 租户命名空间管理 |
| `""` (core) | secrets | get, list, create, delete | 凭证管理 |
| `""` (core) | persistentvolumeclaims | get, list, create, delete | 数据集挂载 |
| `""` (core) | resourcequotas | get, list, create, delete | 租户配额管理 |
| `""` (core) | pods, events | get, list | 日志和状态查询 |
| `networking.k8s.io` | networkpolicies | get, list, create, delete | 租户网络隔离 |
| `rbac.authorization.k8s.io` | roles, rolebindings | get, list, create, update, delete | 租户 RBAC |
| `batch.volcano.sh` | jobs | get, list, create, delete, watch | 训练任务 |
| `scheduling.volcano.sh` | queues, podgroups | get, list | Volcano 调度 |
| `serving.kserve.io` | inferenceservices | get, list, create, delete, patch, watch | 推理服务 |
| `keda.sh` | scaledobjects | get, list, create, delete, patch | 自动扩缩容 |

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
kubectl delete -f infra/k8s/ingress/
kubectl delete -f infra/k8s/labelstudio/
kubectl delete -f infra/k8s/mlflow/
kubectl delete -f infra/k8s/frontend/
kubectl delete -f infra/k8s/backend/
kubectl delete -f infra/k8s/keda/keda.yaml
kubectl delete -f infra/k8s/kserve/kserve.yaml
kubectl delete -f infra/k8s/kserve/kserve-crd.yaml
kubectl delete -f infra/k8s/volcano/volcano.yaml
kubectl delete -f infra/k8s/jupyterhub/jupyterhub.yaml
kubectl delete -f infra/k8s/harbor/harbor.yaml
kubectl delete -f infra/k8s/dcgm-exporter/dcgm-exporter.yaml
kubectl delete -f infra/k8s/prometheus/prometheus.yaml
kubectl delete -f infra/k8s/backend-rbac.yaml
kubectl delete -f infra/k8s/backend-config.yaml
kubectl delete -f infra/k8s/minio/
kubectl delete -f infra/k8s/redis/
kubectl delete -f infra/k8s/postgresql/
kubectl delete -f infra/k8s/namespace.yaml
```
