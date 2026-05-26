import logging
from dataclasses import dataclass

from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

KUBEAI_DATA_DIR = "/data/kubeai"


@dataclass
class PVCInfo:
    name: str
    namespace: str
    storage: str
    labels: dict[str, str]
    creation_timestamp: str | None


async def create_pvc(
    namespace: str,
    pvc_name: str,
    storage_request: str,
    access_mode: str = "ReadWriteMany",
    storage_class: str | None = None,
) -> client.V1PersistentVolumeClaim:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    spec = client.V1PersistentVolumeClaimSpec(
        access_modes=[access_mode],
        resources=client.V1VolumeResourceRequirements(requests={"storage": storage_request}),
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
        return await core_v1.create_namespaced_persistent_volume_claim(namespace=namespace, body=pvc)
    except ApiException as e:
        if e.status == 409:
            return await core_v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
        raise


async def pvc_exists(namespace: str, pvc_name: str) -> bool:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    try:
        await core_v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
        return True
    except ApiException as e:
        if e.status == 404:
            return False
        raise


async def get_pvc(namespace: str, pvc_name: str) -> client.V1PersistentVolumeClaim:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    return await core_v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)


async def delete_pvc(namespace: str, pvc_name: str) -> None:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    try:
        await core_v1.delete_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise


def make_dataset_host_path(tenant_name: str, dataset_name: str, version_number: int) -> str:
    return f"{KUBEAI_DATA_DIR}/datasets/{sanitize_k8s_name(tenant_name)}/{sanitize_k8s_name(dataset_name)}/v{version_number}"


def make_dataset_pvc_name(dataset_name: str, version_number: int) -> str:
    return f"dataset-{sanitize_k8s_name(dataset_name)}-v{version_number}"


async def list_namespace_pvcs(namespace: str) -> list[PVCInfo]:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    try:
        resp = await core_v1.list_namespaced_persistent_volume_claim(namespace=namespace)
        result: list[PVCInfo] = []
        for pvc in resp.items:
            if not pvc.metadata or not pvc.metadata.name:
                continue
            storage = ""
            if pvc.spec and pvc.spec.resources and pvc.spec.resources.requests:
                storage = pvc.spec.resources.requests.get("storage", "")
            result.append(
                PVCInfo(
                    name=pvc.metadata.name,
                    namespace=namespace,
                    storage=storage,
                    labels=pvc.metadata.labels or {},
                    creation_timestamp=pvc.metadata.creation_timestamp.isoformat()
                    if pvc.metadata.creation_timestamp
                    else None,
                )
            )
        return result
    except ApiException:
        logger.exception("list_namespace_pvcs_failed: namespace=%s", namespace)
        return []


async def list_namespace_pods_by_pvc(namespace: str, pvc_name: str) -> list[str]:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    try:
        pods = await core_v1.list_namespaced_pod(namespace=namespace)
        mounted_pods: list[str] = []
        for pod in pods.items:
            if not pod.spec or not pod.metadata or not pod.metadata.name:
                continue
            for volume in pod.spec.volumes or []:
                if volume.persistent_volume_claim and volume.persistent_volume_claim.claim_name == pvc_name:
                    mounted_pods.append(pod.metadata.name)
                    break
        return mounted_pods
    except ApiException:
        logger.exception("list_namespace_pods_by_pvc_failed: namespace=%s pvc=%s", namespace, pvc_name)
        return []


def make_workspace_host_path(tenant_name: str) -> str:
    return f"{KUBEAI_DATA_DIR}/tenant/{sanitize_k8s_name(tenant_name)}/workspace"


def make_user_home_host_path(username: str) -> str:
    return f"{KUBEAI_DATA_DIR}/users/{sanitize_k8s_name(username)}"
