import logging
from typing import Any

from kubernetes import client, config  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_k8s_clients: dict[str, Any] | None = None


def get_k8s_clients() -> dict[str, Any]:
    global _k8s_clients
    if _k8s_clients is not None:
        return _k8s_clients

    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except config.ConfigException:
        config.load_kube_config()
        logger.info("Loaded kubeconfig file")

    core_v1 = client.CoreV1Api()
    networking_v1 = client.NetworkingV1Api()
    batch_v1 = client.BatchV1Api()
    custom_objects = client.CustomObjectsApi()

    _k8s_clients = {
        "core_v1": core_v1,
        "networking_v1": networking_v1,
        "batch_v1": batch_v1,
        "custom_objects": custom_objects,
    }
    return _k8s_clients


def reset_clients() -> None:
    global _k8s_clients
    _k8s_clients = None
