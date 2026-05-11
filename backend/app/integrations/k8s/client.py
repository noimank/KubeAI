import logging
from typing import Any

from kubernetes_asyncio import client, config  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_k8s_clients: dict[str, Any] | None = None


async def get_k8s_clients() -> dict[str, Any]:
    global _k8s_clients
    if _k8s_clients is not None:
        return _k8s_clients

    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except config.ConfigException:
        await config.load_kube_config()
        logger.info("Loaded kubeconfig file")

    api_client = client.ApiClient()
    _k8s_clients = {
        "api_client": api_client,
        "core_v1": client.CoreV1Api(api_client),
        "networking_v1": client.NetworkingV1Api(api_client),
        "batch_v1": client.BatchV1Api(api_client),
        "custom_objects": client.CustomObjectsApi(api_client),
    }
    return _k8s_clients


async def close_k8s_clients() -> None:
    global _k8s_clients
    if _k8s_clients is not None:
        await _k8s_clients["api_client"].close()
        _k8s_clients = None


def reset_clients() -> None:
    global _k8s_clients
    _k8s_clients = None
