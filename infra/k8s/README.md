# KubeAI 独立部署 YAML

按需部署 KubeAI 生产环境组件。每个组件独立维护，可单独部署；本地调试依赖环境使用 `infra/helm/kubeai/`，后端、Taskiq 和前端生产部署统一使用本目录 manifests。

## 目录结构

```
infra/k8s/
├── namespace.yaml               # 命名空间 (必须首先部署)
├── backend-config.yaml          # 后端 ConfigMap + Secret (所有配置项，按需修改)
├── backend-rbac.yaml            # 后端集群权限 (ServiceAccount/ClusterRole/ClusterRoleBinding)
├── 组件说明.md                  # 各组件部署说明索引 (中文)
│
├── postgresql/                  # PostgreSQL 数据库
│   ├── postgresql-secret.yaml   #   数据库密码 (部署前必须修改)
│   └── postgresql.yaml          #   含 mlflow/labelstudio 数据库初始化
├── redis/                       # Redis 缓存
│   └── redis.yaml
├── minio/                       # MinIO 对象存储
│   └── minio.yaml
├── backend/                     # FastAPI 后端 + Taskiq 后台任务
│   ├── deployment.yaml          #   API Deployment，含数据库迁移 initContainer + 健康检查
│   ├── worker.yaml              #   Taskiq Worker，执行开发环境创建/状态同步等async任务
│   ├── beat.yaml                #   Taskiq Scheduler，单副本定时调度状态同步/空闲检查
│   └── service.yaml
├── frontend/                    # React 前端 (Nginx 反向代理 /api → backend)
│   ├── configmap.yaml           #   前端运行时 ConfigMap (APP_TITLE 等，部署前按需修改)
│   ├── deployment.yaml
│   └── service.yaml
├── mlflow/                      # MLflow 实验追踪 (可选)
│   ├── mlflow-secret.yaml       #   数据库连接 URI
│   └── mlflow.yaml
├── labelstudio/                 # Label Studio 数据标注 (可选)
│   ├── labelstudio-secret.yaml  #   数据库密码
│   └── labelstudio.yaml
├── ingress/                     # ApisixRoute 入口 (依赖公司 APISIX 网关)
│   └── ingress.yaml             #   路由到 frontend，APISIX 内部代理 /api 和 /ws
│
├── volcano/                     # Volcano 批处理调度器
│   ├── 00-namespace.yaml        #   volcano-system 命名空间
│   ├── volcano.yaml             #   helm template 渲染，可直接 kubectl apply
│   ├── 99-default-queue.yaml    #   KubeAI VCJob 默认 Queue
│   └── README.md
├── kserve/                      # KServe 模型推理服务
│   ├── 00-namespace.yaml        #   kserve 命名空间
│   ├── kserve-crd.yaml          #   CRDs (helm template 渲染，必须先安装)
│   ├── kserve.yaml              #   Controller + Webhooks
│   ├── kserve-cluster-resources.yaml # ClusterServingRuntime 后置资源
│   ├── README.md
│   └── istio/                   #   Istio 入站链路 (KServe 依赖)
│       ├── istio-operator.yaml  #     IstioOperator 最小化配置
│       ├── istio-manifest.yaml   #     IstioManifest 生成配置 (generate.sh 渲染)
│       ├── kserve-gateway.yaml  #     Gateway + IngressClass
│       ├── install.sh           #     一键安装脚本
│       └── generate.sh           #     Manifest 生成脚本 (helm template + yq)
├── keda/                        # KEDA 自动扩缩容
│   ├── 00-namespace.yaml        #   keda 命名空间
│   ├── keda.yaml                #   helm template 渲染
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
├── monitoring/                  # 监控命名空间
│   └── 00-namespace.yaml        #   monitoring 命名空间 (prometheus/dcgm-exporter 依赖)
└── pull_all_images.sh           # 镜像拉取/推送脚本
```

## 部署前检查清单

部署前请确认以下事项：

| 检查项 | 说明 |
|-------|------|
| Kubernetes 集群 | 可正常连接，`kubectl cluster-info` 通过 |
| 集群权限 | 需要 ClusterAdmin 权限（创建 ClusterRole、ClusterRoleBinding） |
| 节点标签 | 运行 backend/frontend/Taskiq 的节点需打标签: `kubectl label node <node-name> kubeai=true` |
| 镜像就绪 | `kubeai-backend:0.1.0` 和 `kubeai-frontend:0.1.0` 已 build 或可拉取 |
| SECRET_KEY | `backend-config.yaml` 中已替换为随机密钥 (`openssl rand -hex 32`) |
| 数据库密码 | Secret 中 `DATABASE_URL` 密码与 `postgresql/postgresql.yaml` 一致 |
| MinIO 凭证 | Secret 中 `MINIO_ACCESS_KEY/SECRET_KEY` 与 `minio/minio.yaml` 一致 |
| 主机端 `/data/kubeai` 目录 | 见下文 [主机端数据目录准备](#主机端数据目录准备)，否则后端会 `PermissionError` |

## 主机端数据目录准备

后端使用 `hostPath` 把宿主机的 `/data/kubeai` 挂到容器，但镜像内进程以非 root 用户 `kubeai`(UID/GID 999) 运行。
宿主机上如果 `/data/kubeai` 归属 root，容器进程无法 `mkdir /data/kubeai/datasets`，会出现：

```
PermissionError: [Errno 13] Permission denied: '/data/kubeai/datasets'
```

Deployment 已在 `securityContext` 中设置 `fsGroup: 999`，让 kubelet 在挂载时把卷根 chown 到 999；
**但首次部署前**仍需在宿主机上把目录准备好，否则 kubelet 也无权对 root 拥有的目录执行 chown。

**首次部署（仅在第一个会被调度到的工作节点执行）**：

```bash
# 1. 创建目录
sudo mkdir -p /data/kubeai

# 2. 把属主改为镜像内 kubeai 用户的 UID/GID (与 Dockerfile USER kubeai 一致: 999:999)
sudo chown -R 999:999 /data/kubeai

# 3. 给属主/属组读写执行权限 (新建子目录 datasets/ 等会继承)
sudo chmod -R u+rwX,g+rwX /data/kubeai
```

> 如果使用了 `nodeSelector: kubeai=true` 把 backend 固定在特定节点，只需在该节点上执行。

**多节点 (backend 可漂移)**：

hostPath 在多节点上数据不会同步；如果 backend Pod 漂移到其他节点，会看到**空目录**。
如需多节点可用：

- 方案 A：在**所有**可能被调度到的节点上用 `rsync` 同步 `/data/kubeai`（适合小数据量）
- 方案 B：把 `hostPath` 换成 `nfs` / `cephfs` / `local-path` Provisioner（推荐）
- 方案 C：用 nodeAffinity 把 backend 钉死在固定节点 + 配合 PVC 备份

**Pod 已就绪后报错的应急止血**（在 Pod 当前所在节点）：

```bash
sudo chown -R 999:999 /data/kubeai
sudo chmod -R u+rwX,g+rwX /data/kubeai
kubectl -n kubeai rollout restart deploy/backend
```

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
cd backend && uv run taskiq worker app.core.taskiq_app:broker --fs-discover
cd backend && uv run taskiq scheduler app.core.taskiq_app:scheduler --skip-first-run
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

# 5. 后端 API + Taskiq worker/scheduler + 前端
kubectl apply -f infra/k8s/backend/
kubectl apply -f infra/k8s/frontend/

# 6. 可选应用
kubectl apply -f infra/k8s/mlflow/          # 实验追踪
kubectl apply -f infra/k8s/labelstudio/     # 数据标注

# 7. 平台组件 (按需部署)
kubectl apply -f infra/k8s/volcano/00-namespace.yaml
kubectl apply -f infra/k8s/volcano/volcano.yaml
kubectl wait --for=condition=Established --timeout=60s crd/jobs.batch.volcano.sh crd/queues.scheduling.volcano.sh
kubectl apply -f infra/k8s/volcano/99-default-queue.yaml

# KServe 推理链路 (需要 Istio + cert-manager，详见 kserve/README.md)
bash infra/k8s/kserve/istio/install.sh
kubectl apply -f infra/k8s/kserve/00-namespace.yaml
kubectl apply --server-side -f infra/k8s/kserve/kserve-crd.yaml
kubectl wait --for=condition=Established --timeout=60s crd/inferenceservices.serving.kserve.io crd/servingruntimes.serving.kserve.io crd/clusterservingruntimes.serving.kserve.io
kubectl apply -f infra/k8s/kserve/kserve.yaml
kubectl apply --server-side -f infra/k8s/kserve/kserve-cluster-resources.yaml

kubectl apply -f infra/k8s/keda/00-namespace.yaml
kubectl apply --server-side -f infra/k8s/keda/keda.yaml
kubectl apply -f infra/k8s/harbor/harbor.yaml          # 镜像仓库
kubectl apply -f infra/k8s/monitoring/00-namespace.yaml  # 监控命名空间
kubectl apply -f infra/k8s/prometheus/prometheus.yaml  # 监控
```

## 生产部署要点

- `backend/deployment.yaml` 只运行 FastAPI API，可按接口流量水平扩容。
- `backend/worker.yaml` 独立运行 Taskiq worker，按后台任务吞吐单独调整 `spec.replicas`。
- `backend/beat.yaml` 独立运行 Taskiq scheduler，必须保持 `spec.replicas: 1`，避免重复投递定时任务。
- Taskiq 复用 `REDIS_URL` 指向的 Redis，仅通过 `TASKIQ_BROKER_DB` 和 `TASKIQ_RESULT_BACKEND_DB` 区分 broker/result backend DB。
- 已下放到 Taskiq 的后台流程包括开发环境创建、开发环境状态同步、空闲环境检查、推理服务部署、推理服务状态同步和训练任务历史资源清理。

常用运维命令：

```bash
kubectl -n kubeai scale deploy/backend --replicas=3
kubectl -n kubeai scale deploy/backend-taskiq-worker --replicas=2
kubectl -n kubeai get pods -l app.kubernetes.io/component=taskiq-scheduler
kubectl -n kubeai logs deploy/backend-taskiq-worker -f
```

## 组件依赖关系

```
namespace.yaml
  │
  ├── 基础设施
  │   ├── postgresql/        ← mlflow/labelstudio 依赖此数据库
  │   ├── redis/             ← backend + taskiq 依赖
  │   └── minio/             ← backend 依赖
  │
  ├── 应用层
  │   ├── backend/           ← API、Taskiq worker、Taskiq scheduler 独立部署，依赖基础设施 + ConfigMap/Secret/RBAC
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
      │   ├── kserve.yaml       (Controller + Webhooks)
      │   └── istio/            (Istio + Gateway，KServe 入站依赖)
      ├── keda/              ← 推理服务自动扩缩容 (需要 RBAC 权限)
      ├── harbor/            ← 自定义镜像构建
      ├── monitoring/        ← 监控命名空间 (prometheus/dcgm-exporter 依赖)
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

外部访问通过 `kubectl port-forward` 或 Ingress 实现：

组件 Service 均为 ClusterIP，生产环境通过 Ingress 暴露，开发调试使用 `kubectl port-forward`。

## 节点标签

Backend 和 Frontend 组件通过 `nodeSelector` 限制只能调度到带有 `kubeai` 标签的节点上。部署前需要为工作节点打标签：

```bash
# 查看当前节点
kubectl get nodes

# 为节点打上 KubeAI 标签
kubectl label node <node-name> kubeai=true

# 批量打标签 (所有 worker 节点)
kubectl get nodes -l 'node-role.kubernetes.io/worker' -o name | xargs -I {} kubectl label {} kubeai=true
```

> **注意**: 如果所有节点都允许调度 backend/frontend，可以修改 `deployment.yaml` 注释或删除 `nodeSelector` 字段。

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
| 开发环境 | 由 Backend 动态管理 Pod/Service/Ingress，无需额外组件部署 |
| OIDC/SSO | `OIDC_ENABLED: "true"` + Secret 中配置 `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` |
| Harbor | Secret 中配置 `HARBOR_URL` / `HARBOR_PASSWORD` |

## 清理

```bash
kubectl delete -f infra/k8s/ingress/
kubectl delete -f infra/k8s/labelstudio/
kubectl delete -f infra/k8s/mlflow/
kubectl delete -f infra/k8s/frontend/
kubectl delete -f infra/k8s/backend/
kubectl delete -f infra/k8s/keda/keda.yaml --ignore-not-found
kubectl delete -f infra/k8s/keda/00-namespace.yaml --ignore-not-found

kubectl delete -f infra/k8s/kserve/kserve-cluster-resources.yaml --ignore-not-found
kubectl delete -f infra/k8s/kserve/kserve.yaml --ignore-not-found
kubectl delete -f infra/k8s/kserve/kserve-crd.yaml --ignore-not-found
kubectl delete -f infra/k8s/kserve/00-namespace.yaml --ignore-not-found

kubectl delete -f infra/k8s/volcano/99-default-queue.yaml --ignore-not-found
kubectl delete -f infra/k8s/volcano/volcano.yaml --ignore-not-found
kubectl delete -f infra/k8s/volcano/00-namespace.yaml --ignore-not-found
kubectl delete -f infra/k8s/harbor/harbor.yaml
kubectl delete -f infra/k8s/dcgm-exporter/dcgm-exporter.yaml --ignore-not-found
kubectl delete -f infra/k8s/prometheus/prometheus.yaml --ignore-not-found
kubectl delete -f infra/k8s/monitoring/00-namespace.yaml --ignore-not-found
kubectl delete -f infra/k8s/backend-rbac.yaml
kubectl delete -f infra/k8s/backend-config.yaml
kubectl delete -f infra/k8s/minio/
kubectl delete -f infra/k8s/redis/
kubectl delete -f infra/k8s/postgresql/
kubectl delete -f infra/k8s/namespace.yaml
```
