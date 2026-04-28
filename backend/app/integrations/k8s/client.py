import logging

from kubernetes import client, config

logger = logging.getLogger(__name__)

_k8s_clients: dict | None = None


def get_k8s_clients() -> dict:
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

    _k8s_clients = {
        "core_v1": core_v1,
        "networking_v1": networking_v1,
    }
    return _k8s_clients


def reset_clients() -> None:
    global _k8s_clients
    _k8s_clients = None
