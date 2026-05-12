import logging
import re
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from kubernetes_asyncio.client.rest import ApiException

from app.integrations.k8s.client import get_k8s_clients

if TYPE_CHECKING:
    from kubernetes_asyncio import client

logger = logging.getLogger(__name__)

_VCJOB_LABEL = "volcano.sh/job-name"
_ROLE_PATTERN = re.compile(r"-(master|worker)-(\d+)")


def _parse_pod_role(pod_name: str) -> str:
    m = _ROLE_PATTERN.search(pod_name)
    if not m:
        return "master"
    task_role, idx = m.group(1), m.group(2)
    return "master" if task_role == "master" else f"worker-{idx}"


async def stream_pod_logs(
    namespace: str,
    pod_name: str,
    container: str | None = None,
    tail_lines: int = 100,
) -> AsyncGenerator[str, None]:
    from aiohttp import ClientResponse  # noqa: TC002

    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    kwargs: dict[str, Any] = {
        "name": pod_name,
        "namespace": namespace,
        "tail_lines": tail_lines,
        "follow": True,
        "timestamps": True,
        "_preload_content": False,
    }
    if container:
        kwargs["container"] = container

    raw_resp: ClientResponse = await core_v1.read_namespaced_pod_log(**kwargs)  # type: ignore[assignment]
    try:
        async for line in raw_resp.content:
            decoded = line.decode("utf-8").rstrip("\n")
            if decoded:
                yield decoded
    finally:
        raw_resp.close()


async def get_pod_failure_info(namespace: str, pod_name: str) -> dict[str, Any] | None:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        pod = await core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            logger.warning("Pod %s not found in %s", pod_name, namespace)
            return None
        raise

    if not pod.status or not pod.status.container_statuses:
        return None

    for cs in pod.status.container_statuses:
        state = cs.state
        if not state or not state.terminated:
            continue
        t = state.terminated
        return {
            "exit_code": t.exit_code,
            "reason": t.reason or "",
            "message": t.message or "",
            "signal": t.signal,
            "finished_at": str(t.finished_at) if t.finished_at else None,
        }

    for cs in pod.status.container_statuses:
        state = cs.state
        if not state or not state.waiting:
            continue
        if state.waiting.reason in ("ImagePullBackOff", "ErrImagePull"):
            return {
                "exit_code": 0,
                "reason": state.waiting.reason,
                "message": state.waiting.message or "",
                "signal": None,
                "finished_at": None,
            }

    return None


async def list_vcjob_pods(namespace: str, vcjob_name: str) -> list[dict[str, Any]]:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    pods = await core_v1.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"{_VCJOB_LABEL}={vcjob_name}",
    )

    result: list[dict[str, Any]] = []
    for pod in pods.items:
        if not pod.metadata or not pod.status:
            continue
        role = _parse_pod_role(pod.metadata.name)
        result.append(
            {
                "pod_name": pod.metadata.name,
                "role": role,
                "status": pod.status.phase.lower() if pod.status.phase else "unknown",
            }
        )
    return result


async def get_pod_log(
    namespace: str,
    pod_name: str,
    container: str | None = None,
    tail_lines: int = 1000,
) -> str:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    kwargs: dict[str, Any] = {
        "name": pod_name,
        "namespace": namespace,
        "tail_lines": tail_lines,
    }
    if container:
        kwargs["container"] = container

    try:
        log: str = await core_v1.read_namespaced_pod_log(**kwargs)
        return log
    except ApiException as e:
        if e.status == 404 or e.status == 400:
            logger.warning("Pod logs not available for %s: %s", pod_name, e.reason)
            return ""
        raise
