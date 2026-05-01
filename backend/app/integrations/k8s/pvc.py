import logging

from kubernetes import client  # type: ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

from app.integrations.base import with_retry
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)


@with_retry(max_retries=3)
def create_pvc(
    namespace: str,
    pvc_name: str,
    storage_request: str,
    access_mode: str = "ReadWriteMany",
    storage_class: str | None = None,
) -> client.V1PersistentVolumeClaim:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    resources = client.V1ResourceRequirements(requests={"storage": storage_request})
    spec = client.V1PersistentVolumeClaimSpec(
        access_modes=[access_mode],
        resources=resources,
        volume_mode="Filesystem",
    )
    if storage_class:
        spec.storage_class_name = storage_class

    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=pvc_name,
            labels={"app.kubernetes.io/managed-by": "kubeai", "kubeai.io/type": "dataset"},
        ),
        spec=spec,
    )

    try:
        return core_v1.create_namespaced_persistent_volume_claim(namespace=namespace, body=pvc)
    except ApiException as e:
        if e.status == 409:
            return core_v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
        raise


def pvc_exists(namespace: str, pvc_name: str) -> bool:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    try:
        core_v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
        return True
    except ApiException as e:
        if e.status == 404:
            return False
        raise


@with_retry(max_retries=3)
def get_pvc(namespace: str, pvc_name: str) -> client.V1PersistentVolumeClaim:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    return core_v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)


@with_retry(max_retries=3)
def delete_pvc(namespace: str, pvc_name: str) -> None:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    try:
        core_v1.delete_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise


def make_dataset_pvc_name(dataset_id: str, version_id: str) -> str:
    return f"dataset-{dataset_id[:8]}-v{version_id[:8]}"
