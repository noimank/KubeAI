import logging

from kubernetes import client  # type: ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

from app.integrations.base import K8S_NAMESPACE_PREFIX, with_retry
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)


@with_retry(max_retries=3)
def create_namespace(name: str, labels: dict[str, str] | None = None) -> client.V1Namespace:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    ns_labels = {"app.kubernetes.io/managed-by": "kubeai"}
    if labels:
        ns_labels.update(labels)

    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=name, labels=ns_labels),
    )
    return core_v1.create_namespace(body=namespace)


@with_retry(max_retries=3)
def delete_namespace(name: str) -> None:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    core_v1.delete_namespace(name=name)


def namespace_exists(name: str) -> bool:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    try:
        core_v1.read_namespace(name=name)
        return True
    except ApiException as e:
        if e.status == 404:
            return False
        raise


def make_namespace_name(tenant_id: str) -> str:
    return f"{K8S_NAMESPACE_PREFIX}{tenant_id}"
