import logging
from typing import Any

from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.integrations.k8s.client import get_k8s_clients
from app.integrations.k8s.namespace import TENANT_NAMESPACE_LABEL_KEY as TENANT_NS_LABEL_KEY
from app.integrations.k8s.namespace import TENANT_NAMESPACE_LABEL_VALUE as TENANT_NS_LABEL_VALUE

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


async def get_cluster_usage() -> dict[str, str]:
    """Aggregate used resources across all tenant namespaces via ResourceQuota."""
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    namespaces = await core_v1.list_namespace(
        label_selector=f"{TENANT_NS_LABEL_KEY}={TENANT_NS_LABEL_VALUE}",
    )

    total_gpu = 0
    total_cpu = 0
    total_memory = 0
    total_storage = 0

    for ns in namespaces.items:
        used = await get_quota_used(ns.metadata.name)
        total_gpu += int(used.get("requests.nvidia.com/gpu", "0"))
        total_cpu += _parse_cpu(used.get("requests.cpu", "0"))
        total_memory += _parse_memory(used.get("requests.memory", "0"))
        total_storage += _parse_memory(used.get("requests.storage", "0"))

    return {
        "gpu": str(total_gpu),
        "cpu": str(total_cpu),
        "memory": f"{total_memory}Ki",
        "storage": f"{total_storage}Ki",
    }


async def get_node_resource_details() -> list[dict[str, Any]]:
    """Return per-node resource details: allocatable, allocated (via pod requests), and conditions."""
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    nodes = await core_v1.list_node()
    result: list[dict[str, object]] = []

    for node in nodes.items:
        name = node.metadata.name
        allocatable = node.status.allocatable or {}

        alloc_gpu = int(allocatable.get("nvidia.com/gpu", 0))
        alloc_cpu = _parse_cpu(allocatable.get("cpu", "0"))
        alloc_memory = _parse_memory(allocatable.get("memory", "0"))

        pods = await core_v1.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={name},status.phase!=Failed,status.phase!=Succeeded",
        )

        req_cpu = 0
        req_memory = 0
        req_gpu = 0
        for pod in pods.items:
            for container in pod.spec.containers:
                resources = container.resources or client.V1ResourceRequirements()
                requests = resources.requests or {}
                req_cpu += _parse_cpu(requests.get("cpu", "0"))
                req_memory += _parse_memory(requests.get("memory", "0"))
                req_gpu += int(requests.get("nvidia.com/gpu", "0"))

        conditions: list[dict[str, str]] = []
        if node.status.conditions:
            for cond in node.status.conditions:
                conditions.append(
                    {
                        "type": cond.type or "",
                        "status": cond.status or "",
                    }
                )

        result.append(
            {
                "name": name,
                "gpu": {"allocatable": alloc_gpu, "allocated": req_gpu},
                "cpu": {"allocatable": alloc_cpu, "allocated": req_cpu},
                "memory": {"allocatable": alloc_memory, "allocated": req_memory},
                "conditions": conditions,
            }
        )

    return result


async def get_all_tenants_usage() -> list[dict[str, Any]]:
    """Return per-tenant quota and usage from ResourceQuota in each tenant namespace."""
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    namespaces = await core_v1.list_namespace(
        label_selector=f"{TENANT_NS_LABEL_KEY}={TENANT_NS_LABEL_VALUE}",
    )

    result: list[dict[str, object]] = []
    for ns in namespaces.items:
        namespace_name = ns.metadata.name
        try:
            rq = await core_v1.read_namespaced_resource_quota(
                name=RESOURCE_QUOTA_NAME,
                namespace=namespace_name,
            )
        except ApiException as e:
            if e.status == 404:
                continue
            raise

        hard = rq.spec.hard if rq.spec and rq.spec.hard else {}
        used = rq.status.used if rq.status and rq.status.used else {}

        result.append(
            {
                "namespace": namespace_name,
                "quota": {
                    "gpu": int(hard.get("requests.nvidia.com/gpu", 0)),
                    "cpu": hard.get("requests.cpu", "0"),
                    "memory": hard.get("requests.memory", "0"),
                    "storage": hard.get("requests.storage", "0"),
                },
                "used": {
                    "gpu": int(used.get("requests.nvidia.com/gpu", 0)),
                    "cpu": used.get("requests.cpu", "0"),
                    "memory": used.get("requests.memory", "0"),
                    "storage": used.get("requests.storage", "0"),
                },
            }
        )

    return result


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
