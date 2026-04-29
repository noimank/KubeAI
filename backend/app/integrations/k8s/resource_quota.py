import logging

from kubernetes import client  # type: ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

from app.integrations.base import with_retry
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


@with_retry(max_retries=3)
def create_resource_quota(namespace: str, quota: client.V1ResourceQuota) -> client.V1ResourceQuota:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        core_v1.create_namespaced_resource_quota(namespace=namespace, body=quota)
        logger.info("Created ResourceQuota %s in namespace %s", RESOURCE_QUOTA_NAME, namespace)
        return quota
    except ApiException as e:
        if e.status == 409:
            logger.info("ResourceQuota %s already exists in %s", RESOURCE_QUOTA_NAME, namespace)
            return quota
        raise


@with_retry(max_retries=3)
def update_resource_quota(
    namespace: str,
    gpu_limit: int = 0,
    cpu_limit: str = "4",
    memory_limit: str = "8Gi",
    storage_limit: str = "10Gi",
) -> client.V1ResourceQuota:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    quota = build_tenant_resource_quota(gpu_limit, cpu_limit, memory_limit, storage_limit)
    core_v1.replace_namespaced_resource_quota(name=RESOURCE_QUOTA_NAME, namespace=namespace, body=quota)
    logger.info("Updated ResourceQuota %s in namespace %s", RESOURCE_QUOTA_NAME, namespace)
    return quota


@with_retry(max_retries=3)
def delete_resource_quota(namespace: str, name: str = RESOURCE_QUOTA_NAME) -> None:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        core_v1.delete_namespaced_resource_quota(name=name, namespace=namespace)
        logger.info("Deleted ResourceQuota %s from namespace %s", name, namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise
