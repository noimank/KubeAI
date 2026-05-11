import logging

from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.integrations.base import K8S_NAMESPACE_PREFIX, sanitize_k8s_name
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)


async def create_namespace(name: str, labels: dict[str, str] | None = None) -> client.V1Namespace:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    ns_labels = {"app.kubernetes.io/managed-by": "kubeai"}
    if labels:
        ns_labels.update(labels)

    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=name, labels=ns_labels),
    )
    try:
        return await core_v1.create_namespace(body=namespace)
    except ApiException as e:
        if e.status == 409:
            return await core_v1.read_namespace(name=name)
        raise


async def delete_namespace(name: str) -> None:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    await core_v1.delete_namespace(name=name)


async def namespace_exists(name: str) -> bool:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    try:
        await core_v1.read_namespace(name=name)
        return True
    except ApiException as e:
        if e.status == 404:
            return False
        raise


def make_namespace_name(tenant_name: str) -> str:
    return f"{K8S_NAMESPACE_PREFIX}{sanitize_k8s_name(tenant_name)}"
