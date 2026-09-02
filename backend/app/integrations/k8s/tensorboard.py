"""TensorBoard 可视化 K8s 资源管理 — Service + APISIX 动态路由.

镜像 TensorBoard sidecar 由 Volcano VCJob 通过 build_vcjob 注入 (原生 sidecar,
initContainer + restartPolicy=Always), 本模块只负责外部可达层: 为每个启用了
TensorBoard 的训练任务创建 per-job ClusterIP Service 与 APISIX 路由. 作业终结时
由 watcher / 清理路径一并回收.

与 dev_pod 的区别:
  * 不创建 Pod (Pod 由 Volcano 调度)
  * Service selector 指向装了 sidecar 的 master pod (volcano.sh/task-spec=master)
  * 路由原样转发 (无 proxy-rewrite) —— sidecar 以 --path_prefix=/tensorboard/<hex>
    运行, 自行生成带前缀的资源 URL; 仅 forward-auth 鉴权 (Cookie header).
"""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import Any
from urllib.parse import urlparse

import structlog
from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.core.config import settings
from app.integrations.k8s.apisix_admin import delete_route, host_from_frontend_url, put_route
from app.integrations.k8s.client import get_k8s_clients

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENSORBOARD_PATH_PREFIX = "/tensorboard"
TENSORBOARD_LABEL_KEY = "kubeai.io/tensorboard-job-id"

_RESOURCE_LABEL = {
    "app.kubernetes.io/managed-by": "kubeai",
    "app.kubernetes.io/component": "tensorboard",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def _job_id_hex(job_id: uuid.UUID) -> str:
    """UUID as 32-char hex (no dashes) — DNS-safe, URL-safe."""
    return job_id.hex


def _resource_name(job_id: uuid.UUID) -> str:
    return f"tb-{_job_id_hex(job_id)}"


def tensorboard_path(job_id: uuid.UUID) -> str:
    """The URL path prefix for a TensorBoard instance: ``/tensorboard/<hex>``.

    Must match the ``--path_prefix`` injected into the sidecar command by
    ``build_vcjob`` and the APISIX route ``uri``.
    """
    return f"{TENSORBOARD_PATH_PREFIX}/{_job_id_hex(job_id)}"


def tensorboard_access_url(job_id: uuid.UUID) -> str:
    """Full external URL — derived from ``FRONTEND_URL``.

    前端 / 后端通过该 URL 在浏览器跳转或构造下载链接.
    """
    host = settings.FRONTEND_URL.rstrip("/") if settings.FRONTEND_URL else "http://localhost:3000"
    parsed = urlparse(host)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}{tensorboard_path(job_id)}/"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resource_labels(job_id: uuid.UUID) -> dict[str, str]:
    return {**_RESOURCE_LABEL, TENSORBOARD_LABEL_KEY: str(job_id)}


# ---------------------------------------------------------------------------
# Service builder
# ---------------------------------------------------------------------------


def build_tensorboard_service(job_id: uuid.UUID, namespace: str, vcjob_name: str) -> client.V1Service:
    """ClusterIP Service selecting the master pod of the training job.

    Selector 包含两条件:
      * ``volcano.sh/job-name=<vcjob_name>``: 选该 VCJob 的所有 pod
      * ``volcano.sh/task-spec=master``: 仅保留 master task pod (分布式场景),
        避免 worker 被打到 (worker 没有 6006 端口在 listen)

    单 master 训练 (worker_count=1) 同样工作, ``build_vcjob`` 统一将 task 命名
    为 ``master`` (无论 worker_count), 因此 Volcano 给 pod 打的
    ``volcano.sh/task-spec`` 标签始终为 ``master``.
    """
    return client.V1Service(
        metadata=client.V1ObjectMeta(
            name=_resource_name(job_id),
            namespace=namespace,
            labels=_resource_labels(job_id),
        ),
        spec=client.V1ServiceSpec(
            selector={
                "volcano.sh/job-name": vcjob_name,
                "volcano.sh/task-spec": "master",
            },
            ports=[
                client.V1ServicePort(
                    port=settings.TENSORBOARD_PORT,
                    target_port=settings.TENSORBOARD_PORT,
                    name="tb",
                )
            ],
            type="ClusterIP",
        ),
    )


# ---------------------------------------------------------------------------
# APISIX Admin API — route management
# ---------------------------------------------------------------------------


def _build_apisix_route_payload(*, job_id: uuid.UUID, namespace: str) -> dict[str, Any]:
    """Build an APISIX Admin API route payload for a TensorBoard instance.

    Path ``/tensorboard/<hex>/*`` is forwarded **as-is** to the sidecar (no
    proxy-rewrite): the sidecar runs with ``--path_prefix=/tensorboard/<hex>``
    so it serves at that prefix and generates correctly-prefixed asset URLs.
    """
    name = _resource_name(job_id)
    path = tensorboard_path(job_id)
    route_id = _job_id_hex(job_id)

    auth_uri = f"{settings.KUBEAI_BACKEND_INTERNAL_URL}/api/training-jobs/auth-check?job_id={job_id}"
    upstream_node = f"{name}.{namespace}.svc.cluster.local:{settings.TENSORBOARD_PORT}"

    plugins: dict[str, Any] = {
        "forward-auth": {
            "_meta": {"disable": False},
            "uri": auth_uri,
            "request_headers": ["Cookie"],
            "upstream_headers": ["X-KubeAI-User"],
            # Match dev_pod forward-auth tuning: prevent timeout-driven
            # 403 during concurrent request bursts.
            "timeout": 10000,
            "keepalive_pool": 16,
        }
    }

    return {
        "id": route_id,
        "name": name,
        "status": 1,
        "uri": f"{path}/*",
        "host": host_from_frontend_url(),
        "priority": 100,
        "enable_websocket": True,  # TB 2.x data-plane 实时更新走 WebSocket
        "plugins": plugins,
        "upstream": {
            "type": "roundrobin",
            "scheme": "http",
            "nodes": {upstream_node: 1},
            "timeout": {"connect": 15, "send": 60, "read": 60},
        },
    }


# ---------------------------------------------------------------------------
# Lifecycle operations
# ---------------------------------------------------------------------------


class TensorboardManager:
    """Manages K8s Service + APISIX route lifecycle for a single training job's TensorBoard."""

    async def create(self, *, job_id: uuid.UUID, namespace: str, vcjob_name: str) -> None:
        """Create ClusterIP Service for the job's master pod. Push APISIX route (non-fatal)."""
        k8s = await get_k8s_clients()
        core_v1: client.CoreV1Api = k8s["core_v1"]

        svc = build_tensorboard_service(job_id, namespace, vcjob_name)
        name = _resource_name(job_id)

        logger.info("tensorboard_svc_creating", name=name, namespace=namespace, vcjob_name=vcjob_name)

        try:
            await core_v1.create_namespaced_service(namespace=namespace, body=svc)
        except ApiException as e:
            if e.status != 409:
                raise

        # APISIX 路由推送失败不影响训练运行. 用户暂时无法可视化, 但不阻塞作业.
        try:
            await put_route(
                route_id=_job_id_hex(job_id), payload=_build_apisix_route_payload(job_id=job_id, namespace=namespace)
            )
        except Exception:
            logger.warning("tensorboard_apisix_route_create_failed", name=name, exc_info=True)

        logger.info("tensorboard_svc_created", name=name)

    async def delete(self, job_id: uuid.UUID, namespace: str) -> None:
        """Delete APISIX route + K8s Service (swallow 404/any exception)."""
        try:
            await delete_route(route_id=_job_id_hex(job_id))
        except Exception:
            logger.warning("tensorboard_apisix_route_delete_error", job_id=str(job_id))

        try:
            k8s = await get_k8s_clients()
            await k8s["core_v1"].delete_namespaced_service(name=_resource_name(job_id), namespace=namespace)
        except ApiException as e:
            if e.status != 404:
                logger.warning("tensorboard_svc_delete_failed", job_id=str(job_id), error=str(e))


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_tensorboard_manager: TensorboardManager | None = None


def get_tensorboard_manager() -> TensorboardManager:
    global _tensorboard_manager
    if _tensorboard_manager is None:
        _tensorboard_manager = TensorboardManager()
    return _tensorboard_manager
