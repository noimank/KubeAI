"""推理服务对外可达层 — APISIX 动态路由.

与 dev_pod / tensorboard 同构: 为每个 RUNNING 推理服务在 APISIX 推一条路由,
由 forward-auth 回 backend 校验, upstream 直连推理 Service 的 ClusterIP,
不再经 backend Python 反代.

子路径模式 (``InferenceService.subpath_mode``) 决定前缀由谁处理 —— 二选一, 不可两边都剥:

  * ``rewrite`` (默认): proxy-rewrite 剥 ``/inference/<hex>`` 前缀, 上游收到原生路径
    (如 /v1/completions). 适用不透明推理 API (vLLM/TGI), 它们在根路径提供服务.
  * ``native``: 不剥前缀, 原样转发 ``/inference/<hex>/*``. 适用自行处理子路径的 Web 应用
    (如 RemoteBash / Jupyter / RStudio —— 它们按前缀挂载路由并渲染带前缀的资源 URL).
    若对这类应用仍剥前缀, 上游会收到裸 ``/`` 而自身又按前缀路由 → 双重剥离 → 404.

两种模式都注入 ``BASE_URL_PREFIX=/inference/<hex>`` 告知应用平台访问前缀:
rewrite 模式仅用于拼外部 URL, native 模式还用于路由.

  * ``uris`` 同时匹配裸路径 (``/inference/<hex>``) 与带子路径 (``/inference/<hex>/*``),
    避免无尾斜杠的 URL 落到平台 SPA 兜底路由.

推理服务统一为自定义运行时 Deployment + ClusterIP Service (KServe 已移除).
"""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import structlog

from app.core.config import settings
from app.integrations.k8s.apisix_admin import delete_route, host_from_frontend_url, put_route

if TYPE_CHECKING:
    from app.models.inference_service import InferenceService

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INFERENCE_PATH_PREFIX = "/inference"

# 推理可能耗时较长 (大模型 / 批量), upstream 读写超时放宽.
_UPSTREAM_TIMEOUT = {"connect": 15, "send": 600, "read": 600}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def _service_id_hex(service_id: uuid.UUID) -> str:
    """UUID as 32-char hex (no dashes) — DNS-safe, URL-safe, APISIX route_id."""
    return service_id.hex


def _resource_name(service_id: uuid.UUID) -> str:
    return f"inference-{_service_id_hex(service_id)}"


def inference_path(service_id: uuid.UUID) -> str:
    """The URL path prefix for an inference service: ``/inference/<hex>``."""
    return f"{INFERENCE_PATH_PREFIX}/{_service_id_hex(service_id)}"


def inference_access_url(service_id: uuid.UUID, suffix: str = "") -> str:
    """推理服务对外访问 URL — 基于 ``FRONTEND_URL`` 的公网网关地址.

    与 ``tensorboard_access_url`` 同款: 取 scheme://netloc 拼上 /inference/<hex>
    及可选子路径 (model 类型带 ``v1/models/<name>:predict``).
    """
    base = settings.FRONTEND_URL.rstrip("/") if settings.FRONTEND_URL else "http://localhost:3000"
    parsed = urlparse(base)
    url = f"{parsed.scheme}://{parsed.netloc}{inference_path(service_id)}"
    if suffix:
        url = f"{url}/{suffix.lstrip('/')}"
    return url


def _is_route_ready(svc: InferenceService) -> bool:
    """上游 Service 名/端口是否齐备, 可据此构建 upstream node."""
    return bool(svc.k8s_service_name and svc.container_port)


def _stable_upstream_node(svc: InferenceService, namespace: str) -> str:
    """稳定版 upstream node — 集群内 ClusterIP 直连."""
    return f"{svc.k8s_service_name}.{namespace}.svc.cluster.local:{svc.container_port}"


# ---------------------------------------------------------------------------
# APISIX Admin API — route management
# ---------------------------------------------------------------------------


def _build_apisix_route_payload(*, svc: InferenceService, namespace: str) -> dict[str, Any]:
    """Build an APISIX Admin API route payload for an inference service.

    ``uris`` 同时匹配裸路径与带子路径. ``svc.subpath_mode`` 决定是否剥前缀:

    * ``rewrite`` (默认): 加 proxy-rewrite 剥 ``/inference/<hex>`` 前缀, 上游见原生路径.
    * ``native``: 不加 proxy-rewrite, 前缀原样转发, 由应用按 ``BASE_URL_PREFIX`` 自行处理.

    两种模式都注入 ``BASE_URL_PREFIX`` (见 inference_service 部署逻辑); forward-auth /
    uris / upstream / websocket 配置完全一致.
    """
    hex_id = _service_id_hex(svc.id)
    path = inference_path(svc.id)

    auth_uri = f"{settings.KUBEAI_BACKEND_INTERNAL_URL}/api/inference-services/auth-check?service_id={svc.id}"
    stable_node = _stable_upstream_node(svc, namespace)

    plugins: dict[str, Any] = {
        # 浏览器 Cookie (kubeai_access_token JWT) 鉴权, 与 dev_env / tensorboard 统一.
        "forward-auth": {
            "_meta": {"disable": False},
            "uri": auth_uri,
            "request_headers": ["Cookie", "Authorization"],
            "upstream_headers": ["X-KubeAI-User"],
            # Match dev_pod forward-auth tuning: prevent timeout-driven
            # 403 during concurrent request bursts.
            "timeout": 10000,
            "keepalive_pool": 16,
        },
    }
    # rewrite 模式: 剥 /inference/<hex> 前缀, 上游收到原生路径.
    # ^path/?(.*) 只有一个捕获组, 同时覆盖裸路径与带子路径:
    #   /inference/<hex>     → $1=""   → /
    #   /inference/<hex>/foo → $1="foo" → /foo
    # native 模式不加此插件 —— 前缀原样转发, 由应用按 BASE_URL_PREFIX 自行路由 (避免双重剥离).
    if svc.subpath_mode != "native":
        plugins["proxy-rewrite"] = {
            "regex_uri": [f"^{path}/?(.*)", "/$1"],
        }

    payload: dict[str, Any] = {
        "id": hex_id,
        "name": _resource_name(svc.id),
        "status": 1,
        # 同时匹配裸路径与带子路径 —— 裸路径匹配修复 Bug 1 (无尾斜杠 URL 落 SPA).
        "uris": [path, f"{path}/*"],
        "host": host_from_frontend_url(),
        "priority": 100,
        "enable_websocket": True,  # 支持流式 / WebSocket 推理
        "plugins": plugins,
        "upstream": {
            "type": "roundrobin",
            "scheme": "http",
            "nodes": {stable_node: 1},
            "timeout": _UPSTREAM_TIMEOUT,
        },
    }

    return payload


async def put_inference_route(svc: InferenceService, namespace: str) -> None:
    """推送/刷新推理服务的 APISIX 路由. 幂等 — 按 svc 当前字段重建.

    失败只 warn, 不阻塞部署流程 (参照 tensorboard).
    """
    if not _is_route_ready(svc):
        logger.info("inference_route_skip_not_ready", service_id=str(svc.id))
        return
    try:
        await put_route(
            route_id=_service_id_hex(svc.id), payload=_build_apisix_route_payload(svc=svc, namespace=namespace)
        )
        logger.info("inference_route_synced", service_id=str(svc.id))
    except Exception:
        logger.warning("inference_apisix_route_create_failed", service_id=str(svc.id), exc_info=True)


async def delete_inference_route(service_id: uuid.UUID) -> None:
    """删除推理服务的 APISIX 路由. best-effort — 404 即终态."""
    try:
        await delete_route(route_id=_service_id_hex(service_id))
    except Exception:
        logger.warning("inference_apisix_route_delete_failed", service_id=str(service_id))
