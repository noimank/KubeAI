import logging
from typing import Any, cast

from kubernetes_asyncio.client.exceptions import ApiException  # type: ignore[import-untyped]

from app.integrations.base import K8S_NAMESPACE_PREFIX, sanitize_k8s_name
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

VCJOB_GROUP = "batch.volcano.sh"
VCJOB_VERSION = "v1alpha1"
VCJOB_PLURAL = "jobs"


async def create_vcjob(namespace: str, body: dict[str, Any]) -> dict[str, Any]:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        return cast(
            "dict[str, Any]",
            await api.create_namespaced_custom_object(
                group=VCJOB_GROUP,
                version=VCJOB_VERSION,
                namespace=namespace,
                plural=VCJOB_PLURAL,
                body=body,
            ),
        )
    except ApiException as e:
        if e.status == 409:
            logger.info("VCJob %s already exists in %s, ignoring", body.get("metadata", {}).get("name"), namespace)
            return await get_vcjob(namespace, body["metadata"]["name"]) or {}
        raise


async def get_vcjob(namespace: str, name: str) -> dict[str, Any] | None:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        return cast(
            "dict[str, Any]",
            await api.get_namespaced_custom_object(
                group=VCJOB_GROUP,
                version=VCJOB_VERSION,
                namespace=namespace,
                plural=VCJOB_PLURAL,
                name=name,
            ),
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def delete_vcjob(namespace: str, name: str) -> None:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        await api.delete_namespaced_custom_object(
            group=VCJOB_GROUP,
            version=VCJOB_VERSION,
            namespace=namespace,
            plural=VCJOB_PLURAL,
            name=name,
            body={"propagationPolicy": "Background"},
        )
    except ApiException as e:
        if e.status == 404:
            logger.info("VCJob %s not found in %s, ignoring delete", name, namespace)
            return
        raise


async def list_vcjobs(namespace: str) -> list[dict[str, Any]]:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        resp = cast(
            "dict[str, Any]",
            await api.list_namespaced_custom_object(
                group=VCJOB_GROUP,
                version=VCJOB_VERSION,
                namespace=namespace,
                plural=VCJOB_PLURAL,
            ),
        )
        return cast("list[dict[str, Any]]", resp.get("items", []))
    except ApiException as e:
        if e.status == 404:
            return []
        raise


def get_full_namespace(tenant_name: str) -> str:
    return f"{K8S_NAMESPACE_PREFIX}{sanitize_k8s_name(tenant_name)}"


VCJOB_PHASE_MAP: dict[str, str] = {
    "Pending": "pending",
    "Inqueue": "queued",
    "Running": "running",
    "Completed": "succeeded",
    "Failed": "failed",
    "Terminated": "stopped",
}


async def batch_get_vcjob_phases(namespace: str, vcjob_names: list[str]) -> dict[str, str]:
    if not vcjob_names:
        return {}

    result: dict[str, str] = {}

    all_vcjobs = await list_vcjobs(namespace)
    vcjob_map: dict[str, dict[str, Any]] = {v.get("metadata", {}).get("name", ""): v for v in all_vcjobs}

    missing_names: list[str] = []
    for name in vcjob_names:
        vcjob = vcjob_map.get(name)
        if vcjob:
            result[name] = extract_vcjob_phase(vcjob)
        else:
            missing_names.append(name)

    if not missing_names:
        return result

    k8s = await get_k8s_clients()
    core_v1 = k8s["core_v1"]
    missing_set = set(missing_names)
    try:
        pods = await core_v1.list_namespaced_pod(namespace=namespace)
    except ApiException:
        pods = None

    if pods and pods.items:
        pod_phases_by_job: dict[str, list[str]] = {}
        for pod in pods.items:
            if not pod.metadata or not pod.metadata.labels:
                continue
            job_name = pod.metadata.labels.get("batch.volcano.sh/job-name")
            if not job_name or job_name not in missing_set:
                continue
            if pod.status and pod.status.phase:
                pod_phases_by_job.setdefault(job_name, []).append(pod.status.phase)

        for name in missing_names:
            phases = pod_phases_by_job.get(name, [])
            if not phases:
                result[name] = "pending"
            elif "Failed" in phases:
                result[name] = "failed"
            elif all(p == "Succeeded" for p in phases):
                result[name] = "succeeded"
            elif "Running" in phases:
                result[name] = "running"
            else:
                result[name] = "pending"
    else:
        for name in missing_names:
            result[name] = "pending"

    return result


def extract_vcjob_phase(vcjob: dict[str, Any]) -> str:
    phase = vcjob.get("status", {}).get("phase", "Pending")
    mapped = VCJOB_PHASE_MAP.get(phase)
    if mapped is None:
        logger.warning("Unknown VCJob phase %r, falling back to 'pending'", phase)
        return "pending"
    return mapped
