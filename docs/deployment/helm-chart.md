# Helm Chart 配置

## Chart 概述

KubeAI 使用 Helm Chart 进行部署管理，Chart 位于 `infra/helm/kubeai/`。

| 属性 | 值 |
|------|------|
| Chart 名称 | `kubeai` |
| Chart 版本 | `0.1.0` |
| App 版本 | `0.1.0` |
| 维护者 | noimank (noimank@163.com) |

## 依赖组件

| 组件 | Chart | 版本 | 默认启用 | 说明 |
|------|-------|------|----------|------|
| PostgreSQL | Bitnami | 16.7.x | :material-check: | 主数据库 |
| Redis | 自定义 | 7-alpine | :material-check: | 缓存/会话 |
| MinIO | 自定义 | latest | :material-check: | 对象存储 |
| Volcano | Volcano | 1.14.x | :material-check: | 批处理调度 |
| Prometheus Stack | Prometheus | 67.x | :material-check: | 监控 |
| DCGM Exporter | NVIDIA | 3.x | :material-check: | GPU 指标 |
| Harbor | Harbor | 1.16.0 | :material-close: | 镜像仓库 |
| MLflow | 自定义 | v3.12.0 | :material-close: | 实验跟踪 |
| Label Studio | 自定义 | 1.23.0 | :material-close: | 数据标注 |
| JupyterHub | JupyterHub | 4.3.x | :material-close: | 开发环境 |

KServe 通过独立脚本安装：`infra/scripts/install-kserve.sh`

## Values 配置

### 后端配置

```yaml
backend:
  enabled: true
  replicaCount: 1
  image:
    repository: kubeai-backend
    tag: "0.1.0"

  service:
    type: ClusterIP
    port: 8000

  resources:
    requests:
      cpu: 250m
      memory: 256Mi
    limits:
      cpu: "1"
      memory: 512Mi

  # 数据库迁移
  migration:
    enabled: true

  # 持久化存储
  persistence:
    enabled: true
    storageClass: ""
    size: 10Gi
    hostPath: /data/kubeai

  env:
    APP_NAME: "KubeAI"
    APP_VERSION: "0.1.0"
    DEBUG: false
    DB_POOL_SIZE: 20
    REDIS_MAX_CONNECTIONS: 20
    ACCESS_TOKEN_EXPIRE_MINUTES: 30
    REFRESH_TOKEN_EXPIRE_DAYS: 7
    MINIO_BUCKET_PREFIX: "kubeai-datasets-"
    HARBOR_PROJECT_PREFIX: "kubeai-"

  secrets:
    DATABASE_URL: ""         # 必填
    REDIS_URL: ""            # 必填
    SECRET_KEY: ""           # 必填
    MINIO_ACCESS_KEY: ""
    MINIO_SECRET_KEY: ""
    HARBOR_ADMIN_PASSWORD: ""
```

### 前端配置

```yaml
frontend:
  enabled: true
  replicaCount: 1
  image:
    repository: kubeai-frontend
    tag: "0.1.0"

  service:
    type: ClusterIP
    port: 80

  resources:
    requests:
      cpu: 100m
      memory: 64Mi
    limits:
      cpu: 250m
      memory: 128Mi
```

### Ingress 配置

```yaml
ingress:
  enabled: false
  className: ""
  annotations: {}
  hosts:
    - host: kubeai.local
      paths:
        - path: /
          pathType: Prefix
  tls: []
```

### PostgreSQL 配置

```yaml
postgresql:
  enabled: true
  auth:
    postgresPassword: "change-me"
    database: "kubeai"
  primary:
    persistence:
      enabled: true
      size: 10Gi
  initdb:
    scripts:
      # 同时创建 MLflow 和 Label Studio 数据库
      create_dbs.sql: |
        CREATE DATABASE mlflow;
        CREATE DATABASE labelstudio;
```

### Prometheus 配置

```yaml
kube-prometheus-stack:
  enabled: true
  prometheus:
    prometheusSpec:
      retention: 15d
      storageSpec:
        volumeClaimTemplate:
          spec:
            resources:
              requests:
                storage: 20Gi
      # 跨命名空间 ServiceMonitor 发现
      serviceMonitorSelectorNilUsesHelmValues: false
  grafana:
    enabled: true
```

## 安装命令

### 开发环境

```bash
helm install kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values-dev.yaml \
  -n kubeai --create-namespace
```

### 生产环境

```bash
# 创建 Secret（敏感信息）
kubectl create namespace kubeai
kubectl create secret generic kubeai-secrets \
  -n kubeai \
  --from-literal=DATABASE_URL='postgresql+asyncpg://user:pass@postgres:5432/kubeai' \
  --from-literal=REDIS_URL='redis://redis:6379/0' \
  --from-literal=SECRET_KEY='your-strong-secret-key'

# 安装
helm install kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values.yaml \
  -f infra/helm/kubeai/values-prod.yaml \
  -n kubeai
```

## 模板文件

Helm Chart 包含以下模板：

| 模板 | 资源 |
|------|------|
| `backend-deployment.yaml` | 后端 Deployment |
| `backend-service.yaml` | 后端 Service |
| `frontend-deployment.yaml` | 前端 Deployment |
| `frontend-service.yaml` | 前端 Service |
| `ingress.yaml` | Ingress 规则 |
| `secrets.yaml` | Kubernetes Secrets |
| `configmap.yaml` | ConfigMap 配置 |
| `rbac.yaml` | RBAC 权限 |
| `redis.yaml` | Redis StatefulSet |
| `minio.yaml` | MinIO StatefulSet |
| `mlflow.yaml` | MLflow Deployment |
| `labelstudio.yaml` | Label Studio Deployment |
