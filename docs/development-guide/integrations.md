# 集成开发指南

## 概述

KubeAI 通过 `backend/app/integrations/` 目录封装所有外部系统交互。每个集成是一个独立的模块，提供异步或包装为异步的客户端。

## 集成模块一览

| 集成 | 客户端类型 | 异步方式 | 说明 |
|------|-----------|----------|------|
| `k8s/` | `kubernetes_asyncio` | 原生异步 | Kubernetes API |
| `volcano/` | `kubernetes_asyncio` | 原生异步 | Volcano VCJob |
| `kserve/` | `kubernetes_asyncio` | 原生异步 | KServe InferenceService |
| `keda/` | `kubernetes_asyncio` | 原生异步 | KEDA ScaledObject |
| `minio/` | `minio` (同步) | `asyncio.to_thread()` | MinIO S3 |
| `harbor/` | `httpx` (同步) | `asyncio.to_thread()` | Harbor REST API |
| `mlflow/` | `httpx` (同步) | `asyncio.to_thread()` | MLflow REST API |
| `labelstudio/` | `httpx` (同步) | `asyncio.to_thread()` | Label Studio REST API |
| `jupyterhub/` | `httpx` (同步) | `asyncio.to_thread()` | JupyterHub REST API |
| `prometheus/` | `httpx` (同步) | `asyncio.to_thread()` | Prometheus HTTP API |

## Kubernetes 集成

### 客户端管理

K8s 客户端通过 `get_k8s_clients()` 获取，使用后通过 `close_k8s_clients()` 关闭：

```python
from app.integrations.k8s import get_k8s_clients, close_k8s_clients

async def my_function():
    core_v1, batch_v1, custom_api = await get_k8s_clients()
    try:
        # 使用客户端...
        ns = await core_v1.read_namespace(name="kubeai-default")
    finally:
        await close_k8s_clients()
```

### 子模块

| 模块 | 功能 |
|------|------|
| `namespace.py` | 命名空间 CRUD |
| `job.py` | Kubernetes Job 管理 |
| `pod.py` | Pod 查询和日志 |
| `deployment.py` | Deployment 管理 |
| `secret.py` | Secret CRUD |
| `pvc.py` | PersistentVolumeClaim 管理 |
| `resource_quota.py` | ResourceQuota 管理 |
| `network_policy.py` | NetworkPolicy 管理 |
| `upload_job.py` | 文件上传 Job 编排 |

### Builder 模式

部分集成使用 Builder 模式构建 K8s 资源：

```python
# Volcano Job Builder
from app.integrations.volcano.job_builder import VolcanoJobBuilder

job_spec = (
    VolcanoJobBuilder()
    .with_name("training-42")
    .with_namespace("kubeai-tenant-1")
    .with_image("pytorch:2.1-cuda12")
    .with_command("python train.py")
    .with_cpu("4")
    .with_gpu(2)
    .build()
)
```

```python
# KServe Builder
from app.integrations.kserve.builder import InferenceServiceBuilder

isvc_spec = (
    InferenceServiceBuilder()
    .with_name("my-model")
    .with_namespace("kubeai-tenant-1")
    .with_model_uri("s3://bucket/model")
    .with_framework("pytorch")
    .with_gpu(1)
    .build()
)
```

## 添加新集成

### 步骤

1. 在 `integrations/` 下创建新目录
2. 实现 `client.py`（客户端类）
3. 在 `core/config.py` 中添加配置项
4. 在 `core/events.py` 中初始化客户端
5. 在服务层使用客户端

### 同步集成模板

```python
# integrations/new_service/client.py
class NewServiceClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def _request(self, method: str, path: str, **kwargs):
        """同步 HTTP 请求"""
        import httpx
        response = httpx.request(
            method,
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def list_items(self):
        return self._request("GET", "/items")

    def close(self):
        pass  # 清理资源
```

在服务层使用：

```python
class MyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_items(self):
        client = get_new_service_client()
        # 同步调用包装为异步
        return await asyncio.to_thread(client.list_items)
```

### 异步集成模板

```python
# integrations/new_k8s_service/client.py
from kubernetes_asyncio import client as k8s_client

class NewK8sServiceClient:
    async def create_resource(self, namespace: str, spec: dict):
        api = k8s_client.CustomObjectsApi()
        return await api.create_namespaced_custom_object(
            group="example.com",
            version="v1",
            namespace=namespace,
            plural="resources",
            body=spec,
        )
```

## 客户端生命周期

所有集成客户端在应用启动时初始化，关闭时清理：

- **启动**：`core/events.py` 的 `on_startup()` 函数
- **关闭**：`core/events.py` 的 `on_shutdown()` 函数
- **访问**：通过模块级 getter 函数（如 `get_minio_client()`）

!!! note "注意"
    确保在 `on_shutdown()` 中正确关闭所有客户端连接，避免资源泄漏。
