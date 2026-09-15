# 生产环境部署

## 定位

生产部署统一使用 `infra/k8s/` 下的 Kubernetes manifests。`infra/helm/kubeai/` 只用于本地调试依赖环境，不承担生产部署职责。

## 前提条件

- Kubernetes >= 1.28
- 至少 3 个工作节点
- NVIDIA GPU Operator（如需 GPU 支持）
- 默认 StorageClass 或已按 manifests 调整存储配置
- 已构建并推送 `kubeai-backend:0.1.0`、`kubeai-frontend:0.1.0`

## 部署步骤

### 1. 准备命名空间

```bash
kubectl apply -f infra/k8s/namespace.yaml
```

### 2. 修改配置

部署前修改：

- `infra/k8s/backend-config.yaml`：数据库、Redis、MinIO、Harbor、APISIX、域名、密钥等配置
- `infra/k8s/ingress/ingress.yaml`：生产域名和 TLS
- `infra/k8s/backend/`、`infra/k8s/frontend/`：镜像仓库、资源规格、副本数、调度策略

Taskiq 复用 `REDIS_URL`，只通过 `TASKIQ_BROKER_DB` 和 `TASKIQ_RESULT_BACKEND_DB` 区分 broker/result backend DB。

### 3. 部署基础设施

```bash
kubectl apply -f infra/k8s/postgresql/
kubectl apply -f infra/k8s/redis/
kubectl apply -f infra/k8s/minio/
kubectl apply -f infra/k8s/volcano/00-namespace.yaml
kubectl apply -f infra/k8s/volcano/volcano.yaml
kubectl apply -f infra/k8s/volcano/99-default-queue.yaml
kubectl apply -f infra/k8s/keda/00-namespace.yaml
kubectl apply --server-side -f infra/k8s/keda/keda.yaml
kubectl apply -f infra/k8s/kserve/00-namespace.yaml
kubectl apply --server-side -f infra/k8s/kserve/kserve-crd.yaml
kubectl apply -f infra/k8s/kserve/kserve.yaml
kubectl apply --server-side -f infra/k8s/kserve/kserve-cluster-resources.yaml
```

按需部署：

```bash
kubectl apply -f infra/k8s/harbor/
kubectl apply -f infra/k8s/mlflow/
kubectl apply -f infra/k8s/prometheus/
kubectl apply -f infra/k8s/dcgm-exporter/
```

### 4. 部署应用

```bash
kubectl apply -f infra/k8s/backend-config.yaml
kubectl apply -f infra/k8s/backend-rbac.yaml
kubectl apply -f infra/k8s/backend/
kubectl apply -f infra/k8s/frontend/
kubectl apply -f infra/k8s/ingress/
```

`infra/k8s/backend/` 中后端 API、Taskiq worker、Taskiq scheduler 是独立 Deployment：

- `backend/deployment.yaml`：FastAPI API，可按接口流量扩容
- `backend/worker.yaml`：Taskiq worker，可按后台任务吞吐扩容
- `backend/beat.yaml`：Taskiq scheduler，必须保持 1 副本

已下放到 Taskiq 的后台流程包括开发环境创建/同步/空闲检查、推理服务部署/同步、训练任务历史资源清理。

## 验证

```bash
kubectl get pods -n kubeai
kubectl get deploy -n kubeai
kubectl get svc -n kubeai
kubectl logs -n kubeai deploy/backend-taskiq-worker -f
kubectl logs -n kubeai deploy/backend-taskiq-scheduler -f
```

健康检查：

```bash
kubectl port-forward -n kubeai svc/backend 8000:8000
curl http://localhost:8000/api/health
```

## 高可用

生产扩容直接修改 `infra/k8s` manifests：

- API：调整 `infra/k8s/backend/deployment.yaml` 的 `spec.replicas`
- Worker：调整 `infra/k8s/backend/worker.yaml` 的 `spec.replicas`
- Beat：保持 `infra/k8s/backend/beat.yaml` 的 `spec.replicas: 1`
- 前端：调整 `infra/k8s/frontend/deployment.yaml` 的 `spec.replicas`

数据库、Redis、MinIO、Harbor 的高可用建议使用外部托管服务或专用 Operator，并在 `backend-config.yaml` 中指向外部地址。

## 监控

Prometheus/Grafana 使用 `infra/k8s/prometheus/` 部署。GPU 监控使用 `infra/k8s/dcgm-exporter/`，需要节点具备 NVIDIA 运行时和驱动。

## 备份

数据库和对象存储备份策略应按生产存储方案制定。使用内置 manifests 时，至少定期备份 PostgreSQL 数据库和 MinIO 数据目录/PVC。

## 升级

1. 构建并推送新版本后端/前端镜像。
2. 更新 `infra/k8s/backend/*.yaml`、`infra/k8s/frontend/*.yaml` 中的镜像 tag。
3. 执行：

```bash
kubectl apply -f infra/k8s/backend/
kubectl apply -f infra/k8s/frontend/
kubectl rollout status -n kubeai deploy/backend
kubectl rollout status -n kubeai deploy/backend-taskiq-worker
kubectl rollout status -n kubeai deploy/frontend
```
