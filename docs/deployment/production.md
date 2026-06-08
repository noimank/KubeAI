# 生产环境部署

## 前提条件

### Kubernetes 集群

- Kubernetes >= 1.28
- 至少 3 个工作节点
- NVIDIA GPU Operator（如需 GPU 支持）
- 默认 StorageClass 配置

### 硬件建议

| 规模 | 节点数 | CPU/节点 | 内存/节点 | GPU/节点 | 存储 |
|------|--------|----------|-----------|----------|------|
| 小型 | 3 | 8 核 | 32 GB | 0-2 | 500 GB |
| 中型 | 5 | 16 核 | 64 GB | 2-4 | 1 TB |
| 大型 | 10+ | 32 核 | 128 GB | 4-8 | 2+ TB |

## 部署步骤

### 1. 准备命名空间

```bash
kubectl create namespace kubeai
```

### 2. 配置 Secrets

```bash
kubectl create secret generic kubeai-secrets \
  -n kubeai \
  --from-literal=DATABASE_URL='postgresql+asyncpg://kubeai:STRONG_PASSWORD@postgres:5432/kubeai' \
  --from-literal=REDIS_URL='redis://redis:6379/0' \
  --from-literal=SECRET_KEY='YOUR_RANDOM_SECRET_KEY_AT_LEAST_32_CHARS' \
  --from-literal=MINIO_ROOT_PASSWORD='STRONG_MINIO_PASSWORD' \
  --from-literal=HARBOR_ADMIN_PASSWORD='STRONG_HARBOR_PASSWORD'
```

### 3. 安装 KServe 和 KEDA

```bash
# 安装 KServe
kubectl apply -f infra/k8s/kserve/00-namespace.yaml
kubectl apply --server-side -f infra/k8s/kserve/kserve-crd.yaml
kubectl wait --for=condition=Established --timeout=60s crd/inferenceservices.serving.kserve.io crd/servingruntimes.serving.kserve.io crd/clusterservingruntimes.serving.kserve.io
kubectl apply -f infra/k8s/kserve/kserve.yaml
kubectl apply --server-side -f infra/k8s/kserve/kserve-cluster-resources.yaml

# 安装 KEDA
kubectl apply -f infra/k8s/keda/00-namespace.yaml
kubectl apply --server-side -f infra/k8s/keda/keda.yaml
```

### 4. 安装 Volcano 调度器

```bash
kubectl apply -f infra/k8s/volcano/00-namespace.yaml
kubectl apply -f infra/k8s/volcano/volcano.yaml
kubectl wait --for=condition=Established --timeout=60s crd/jobs.batch.volcano.sh crd/queues.scheduling.volcano.sh
kubectl apply -f infra/k8s/volcano/99-default-queue.yaml
```

### 5. 安装 KubeAI

```bash
helm install kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values.yaml \
  -f infra/helm/kubeai/values-prod.yaml \
  -n kubeai \
  --timeout 10m
```

### 6. 验证部署

```bash
# 检查 Pod 状态
kubectl get pods -n kubeai

# 检查服务
kubectl get svc -n kubeai

# 检查健康状态
kubectl port-forward svc/kubeai-backend 8000:8000 -n kubeai
curl http://localhost:8000/api/health
```

## 安全配置

### 网络策略

生产环境建议启用 NetworkPolicy：

- 租户间网络隔离
- 限制对外访问
- 仅允许必要的服务间通信

### TLS 配置

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  tls:
    - hosts:
        - kubeai.example.com
      secretName: kubeai-tls
  hosts:
    - host: kubeai.example.com
      paths:
        - path: /
          pathType: Prefix
```

### 资源限制

确保所有 Pod 都配置了资源请求和限制：

```yaml
backend:
  resources:
    requests:
      cpu: "1"
      memory: 512Mi
    limits:
      cpu: "2"
      memory: 1Gi
```

## 高可用

### 后端多副本

```yaml
backend:
  replicaCount: 3
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchLabels:
                app: kubeai-backend
            topologyKey: kubernetes.io/hostname
```

### 数据库高可用

建议使用外部管理的 PostgreSQL 服务（如 AWS RDS、Azure Database for PostgreSQL）：

```yaml
postgresql:
  enabled: false  # 使用外部数据库

backend:
  secrets:
    DATABASE_URL: "postgresql+asyncpg://user:pass@rds-endpoint:5432/kubeai"
```

### Redis 高可用

建议使用 Redis Sentinel 或外部管理的 Redis 服务：

```yaml
# values-prod.yaml
redis:
  enabled: false  # 使用外部 Redis

backend:
  secrets:
    REDIS_URL: "redis://redis-endpoint:6379/0"
```

## 监控

### Prometheus + Grafana

Chart 默认部署 Prometheus 和 Grafana：

```yaml
kube-prometheus-stack:
  enabled: true
  grafana:
    adminPassword: "STRONG_GRAFANA_PASSWORD"
  prometheus:
    prometheusSpec:
      retention: 30d
```

### GPU 监控

确保 DCGM Exporter 正常运行：

```bash
kubectl get pods -n kubeai -l app=dcgm-exporter
```

## 备份

### 数据库备份

```bash
# PostgreSQL 备份
kubectl exec -n kubeai postgres-0 -- pg_dump -U postgres kubeai > kubeai_backup.sql
```

### MinIO 数据备份

配置 MinIO 的生命周期策略和版本控制，或使用 mc mirror 同步到外部存储。

## 升级

```bash
# 更新镜像版本后
helm upgrade kubeai infra/helm/kubeai/ \
  -f infra/helm/kubeai/values.yaml \
  -f infra/helm/kubeai/values-prod.yaml \
  -n kubeai
```

升级前确保运行数据库迁移：

```bash
# 后端 Pod 启动时自动运行迁移（如果 migration.enabled=true）
```
