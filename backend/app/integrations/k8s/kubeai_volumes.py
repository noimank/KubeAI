"""KubeAI Pod 共享卷 / 环境变量 / chown initContainer 组装.

开发环境 (dev_pod) 与推理服务 (inference Deployment) 都需要把 KubeAI 的共享
hostPath 目录 (/kubeai/home, /kubeai/workspace, 可选数据集) 挂进 Pod, 并:
  * 用 busybox initContainer 以 root 身份把 /kubeai 递归 chown 到 1000:100,
    让非根主容器 (UID 1000) 可写;
  * 注入 KUBEAI_* / HOME / SHELL 环境变量.

本模块提供纯 dict 构建器 (给 `build_deployment` 用). 开发环境的 V1 对象形态
initContainer 留在 dev_pod.py (kubernetes_asyncio 路径), 不强制走 dict 形态
以避免大面积回归 — 仅数据集卷是 dev 独有, 由 dev service 自行 append.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.pvc import make_user_home_host_path, make_workspace_host_path

KUBEAI_CONTAINER_ROOT = "/kubeai"
HOME_MOUNT_PATH = f"{KUBEAI_CONTAINER_ROOT}/home"
WORKSPACE_MOUNT_PATH = f"{KUBEAI_CONTAINER_ROOT}/workspace"
MODEL_MOUNT_PATH = f"{KUBEAI_CONTAINER_ROOT}/models"

# 非根运行 UID/GID (与 dev_pod.py security context 一致).
_RUN_UID = 1000
_RUN_GID = 100


def dataset_mount_path(dataset_name: str, version_number: int) -> str:
    """数据集在容器内的挂载路径: /kubeai/datasets/<name>/v<n>."""
    return f"{KUBEAI_CONTAINER_ROOT}/datasets/{sanitize_k8s_name(dataset_name)}/v{version_number}"


def build_kubeai_volumes(*, username: str, tenant_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """构建 home + workspace 两个 hostPath 卷及其挂载点.

    返回 (volumes, volume_mounts), 形态与 `build_deployment` 的入参一致.
    数据集卷是开发环境独有, 由调用方自行 append.
    """
    volumes: list[dict[str, Any]] = [
        {"name": "home-volume", "hostPath": {"path": make_user_home_host_path(username), "type": "DirectoryOrCreate"}},
        {
            "name": "workspace-volume",
            "hostPath": {"path": make_workspace_host_path(tenant_name), "type": "DirectoryOrCreate"},
        },
    ]
    mounts: list[dict[str, Any]] = [
        {"name": "home-volume", "mountPath": HOME_MOUNT_PATH},
        {"name": "workspace-volume", "mountPath": WORKSPACE_MOUNT_PATH},
    ]
    return volumes, mounts


def build_kubeai_env_vars(*, env_id: str | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    """构建 KUBEAI_* / HOME / SHELL 环境变量块.

    框架键 (KUBEAI_*, HOME, SHELL) 优先于 extra, 与开发环境旧行为一致:
    merged = dict(extra); merged.update(<框架键>).
    """
    merged: dict[str, str] = dict(extra or {})
    if env_id:
        merged["KUBEAI_ENV_ID"] = env_id
    merged["KUBEAI_ROOT_PATH"] = KUBEAI_CONTAINER_ROOT
    merged["KUBEAI_WORKSPACE_PATH"] = WORKSPACE_MOUNT_PATH
    merged["KUBEAI_HOME_PATH"] = HOME_MOUNT_PATH
    merged["HOME"] = HOME_MOUNT_PATH  # 让 shell/tools 用持久化 home
    merged["SHELL"] = "/bin/bash"  # 终端集成
    return merged


def build_chown_init_container(*, name: str, volume_mounts: list[dict[str, Any]]) -> dict[str, Any]:
    """构建 busybox chown initContainer (dict 形态, 给 build_deployment).

    以 root 身份递归 chown /kubeai 到 1000:100, 让非根主容器可写挂载目录.
    V1 对象形态的等价物在 dev_pod.py.
    """
    return {
        "name": name,
        "image": settings.BUSYBOX_IMAGE,
        "command": ["sh", "-c"],
        "args": [f"chown -R {_RUN_UID}:{_RUN_GID} {KUBEAI_CONTAINER_ROOT} 2>/dev/null; echo 'init done'"],
        "volumeMounts": volume_mounts,
        "resources": {
            "requests": {"cpu": "50m", "memory": "32Mi"},
            "limits": {"cpu": "100m", "memory": "64Mi"},
        },
        "securityContext": {"runAsUser": 0, "runAsGroup": 0},
    }


def build_models_host_path(tenant_name: str) -> str:
    """模型 hostPath: /data/kubeai/models/<sanitized_tenant>."""
    return f"/data/kubeai/models/{sanitize_k8s_name(tenant_name)}"


def build_models_volume(tenant_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """构建模型 hostPath 卷及其挂载点.

    返回 (volume, volume_mount), 形态与 `build_deployment` 的入参一致.
    模型卷挂载到 /kubeai/models/.
    """
    host_path = build_models_host_path(tenant_name)
    vol: dict[str, Any] = {"name": "models-volume", "hostPath": {"path": host_path, "type": "DirectoryOrCreate"}}
    mnt: dict[str, Any] = {"name": "models-volume", "mountPath": MODEL_MOUNT_PATH}
    return vol, mnt


def build_model_pull_init_container(
    *,
    name: str,
    minio_bucket: str,
    storage_path: str,
    volume_mounts: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建 model-pull initContainer (dict 形态).

    使用 minio/mc 从 MinIO 拉取模型到本地卷 (/kubeai/models/).
    凭证通过 s3-credentials Secret (envFrom) 注入, 与 upload_job.py 模式一致.
    """
    return {
        "name": name,
        "image": settings.MINIO_MC_IMAGE,
        "command": ["/bin/sh", "-c"],
        "args": [
            "mc alias set kubeai $AWS_ENDPOINT_URL $AWS_ACCESS_KEY_ID $AWS_SECRET_ACCESS_KEY\n"
            f"mc cp --recursive kubeai/$MINIO_BUCKET/$STORAGE_PATH/ {MODEL_MOUNT_PATH}/"
        ],
        "env": [
            {"name": "MINIO_BUCKET", "value": minio_bucket},
            {"name": "STORAGE_PATH", "value": storage_path},
        ],
        "envFrom": [{"secretRef": {"name": "s3-credentials"}}],
        "volumeMounts": volume_mounts,
        "resources": {
            "requests": {"cpu": "100m", "memory": "128Mi"},
            "limits": {"cpu": "500m", "memory": "256Mi"},
        },
    }
