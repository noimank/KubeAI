import logging

from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

RESOURCE_QUOTA_NAME = "tenant-default-quota"


def build_tenant_resource_quota(
    gpu_limit: int = 0,
    cpu_limit: str = "4",
    memory_limit: str = "8Gi",
    storage_limit: str = "10Gi",
) -> client.V1ResourceQuota:
    return client.V1ResourceQuota(
        api_version="v1",
        kind="ResourceQuota",
        metadata=client.V1ObjectMeta(name=RESOURCE_QUOTA_NAME),
        spec=client.V1ResourceQuotaSpec(
            hard={
                "requests.cpu": cpu_limit,
                "requests.memory": memory_limit,
                "requests.storage": storage_limit,
                "requests.nvidia.com/gpu": str(gpu_limit),
            },
        ),
    )


async def create_resource_quota(namespace: str, quota: client.V1ResourceQuota) -> client.V1ResourceQuota:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        await core_v1.create_namespaced_resource_quota(namespace=namespace, body=quota)
        logger.info("Created ResourceQuota %s in namespace %s", RESOURCE_QUOTA_NAME, namespace)
        return quota
    except ApiException as e:
        if e.status == 409:
            logger.info("ResourceQuota %s already exists in %s", RESOURCE_QUOTA_NAME, namespace)
            return quota
        raise


async def update_resource_quota(
    namespace: str,
    gpu_limit: int = 0,
    cpu_limit: str = "4",
    memory_limit: str = "8Gi",
    storage_limit: str = "10Gi",
) -> client.V1ResourceQuota:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    quota = build_tenant_resource_quota(gpu_limit, cpu_limit, memory_limit, storage_limit)
    try:
        await core_v1.replace_namespaced_resource_quota(name=RESOURCE_QUOTA_NAME, namespace=namespace, body=quota)
        logger.info("Updated ResourceQuota %s in namespace %s", RESOURCE_QUOTA_NAME, namespace)
    except ApiException as e:
        if e.status == 404:
            await create_resource_quota(namespace=namespace, quota=quota)
            logger.info("Created ResourceQuota %s in namespace %s (was missing)", RESOURCE_QUOTA_NAME, namespace)
        else:
            raise
    return quota


async def delete_resource_quota(namespace: str, name: str = RESOURCE_QUOTA_NAME) -> None:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        await core_v1.delete_namespaced_resource_quota(name=name, namespace=namespace)
        logger.info("Deleted ResourceQuota %s from namespace %s", name, namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise


async def get_cluster_capacity() -> dict[str, str]:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    nodes = await core_v1.list_node()
    total_gpu = 0
    total_cpu = 0
    total_memory = 0

    for node in nodes.items:
        allocatable = node.status.allocatable or {}
        total_gpu += int(allocatable.get("nvidia.com/gpu", 0))
        cpu_str = allocatable.get("cpu", "0")
        total_cpu += _parse_cpu(cpu_str)
        mem_str = allocatable.get("memory", "0")
        total_memory += _parse_memory(mem_str)

    return {
        "gpu": str(total_gpu),
        "cpu": str(total_cpu),
        "memory": f"{total_memory}Ki",
    }


async def get_quota_used(namespace: str) -> dict[str, str]:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        rq = await core_v1.read_namespaced_resource_quota(name=RESOURCE_QUOTA_NAME, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return {
                "requests.nvidia.com/gpu": "0",
                "requests.cpu": "0",
                "requests.memory": "0",
                "requests.storage": "0",
            }
        raise

    used = rq.status.used if rq.status and rq.status.used else {}
    return {
        "requests.nvidia.com/gpu": used.get("requests.nvidia.com/gpu", "0"),
        "requests.cpu": used.get("requests.cpu", "0"),
        "requests.memory": used.get("requests.memory", "0"),
        "requests.storage": used.get("requests.storage", "0"),
    }


def _parse_cpu(value: str) -> int:
    if value.endswith("m"):
        return int(value[:-1]) // 1000
    return int(value)


def _parse_memory(value: str) -> int:
    suffixes = {"Ki": 1, "Mi": 1024, "Gi": 1024**2, "Ti": 1024**3}
    for suffix, multiplier in suffixes.items():
        if value.endswith(suffix):
            return int(value[: -len(suffix)]) * multiplier
    return int(value)
