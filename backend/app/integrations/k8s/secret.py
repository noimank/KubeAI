import base64
import logging

from kubernetes import client  # type: ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

from app.integrations.base import with_retry
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)


def _encode_secret_data(data: dict[str, str]) -> dict[str, str]:
    return {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}


@with_retry(max_retries=3)
def create_secret(namespace: str, name: str, data: dict[str, str]) -> client.V1Secret:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    secret = client.V1Secret(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        type="Opaque",
        data=_encode_secret_data(data),
    )

    try:
        core_v1.create_namespaced_secret(namespace=namespace, body=secret)
        logger.info("Created Secret %s in namespace %s", name, namespace)
        return secret
    except ApiException as e:
        if e.status == 409:
            core_v1.replace_namespaced_secret(name=name, namespace=namespace, body=secret)
            logger.info("Updated Secret %s in namespace %s", name, namespace)
            return secret
        raise


@with_retry(max_retries=3)
def delete_secret(namespace: str, name: str) -> None:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        core_v1.delete_namespaced_secret(name=name, namespace=namespace)
        logger.info("Deleted Secret %s from namespace %s", name, namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise


def get_secret(namespace: str, name: str) -> dict[str, str] | None:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        secret = core_v1.read_namespaced_secret(name=name, namespace=namespace)
        decoded = {}
        if secret.data:
            for k, v in secret.data.items():
                decoded[k] = base64.b64decode(v).decode()
        return decoded
    except ApiException as e:
        if e.status == 404:
            return None
        raise


def make_secret_name(tenant_id: str, credential_name: str) -> str:
    return f"credential-{tenant_id}-{credential_name}"
