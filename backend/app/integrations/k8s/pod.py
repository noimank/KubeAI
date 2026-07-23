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
_WORKER_INDEX_PATTERN = re.compile(r"worker-(\d+)")


def _parse_pod_role(pod_name: str) -> str:
    m = _ROLE_PATTERN.search(pod_name)
    if not m:
        return "master"
    task_role, idx = m.group(1), m.group(2)
    return "master" if task_role == "master" else f"worker-{idx}"


def _pod_order_key(pod: dict[str, Any]) -> tuple[int, int]:
    """Sort master first, then workers by index — gives a deterministic default
    pod (the chief) for distributed jobs instead of relying on K8s API order."""
    role = pod.get("role", "")
    if role == "master":
        return (0, 0)
    m = _WORKER_INDEX_PATTERN.match(role)
    if m:
        return (1, int(m.group(1)))
    return (2, 0)


async def stream_pod_logs(
    namespace: str,
    pod_name: str,
    container: str | None = None,
    tail_lines: int = 100,
) -> AsyncGenerator[str, None]:
    from aiohttp import ClientError, ClientResponse

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

    try:
        raw_resp: ClientResponse = await core_v1.read_namespaced_pod_log(**kwargs)  # type: ignore[assignment]
    except ApiException as e:
        # 400: container not yet running (Pending / ContainerCreating); 404: pod gone.
        # End gracefully — the client reconnects and retries once logs are available,
        # matching get_pod_log's tolerance rather than surfacing a 500.
        if e.status in (400, 404):
            logger.warning("Pod logs not streamable for %s: %s", pod_name, e.reason)
            return
        raise

    try:
        async for line in raw_resp.content:
            decoded = line.decode("utf-8").rstrip("\n")
            if decoded:
                yield decoded
    except ClientError as e:
        # Mid-stream hiccup (connection reset, idle timeout). End cleanly so the
        # client reconnects instead of surfacing a 500. CancelledError propagates.
        logger.warning("Log stream interrupted for %s: %s", pod_name, e)
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
    result.sort(key=_pod_order_key)
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
        "timestamps": True,
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


# ---------------------------------------------------------------------------
# Failure reason — shared by TrainingJobService and the pod watcher
# ---------------------------------------------------------------------------


def map_failure_message(failure: dict[str, Any]) -> str:
    """Map a K8s container termination to a Chinese, human-readable message."""
    reason = failure.get("reason", "")
    exit_code = failure.get("exit_code", -1)

    if reason == "OOMKilled":
        return "内存不足 (OOM)：训练容器因超出内存限制被终止。建议增加内存配置或优化训练脚本。"
    if reason in ("ImagePullBackOff", "ErrImagePull"):
        return "镜像拉取失败：请检查镜像地址是否正确，以及是否具有拉取权限。"
    if reason == "ContainerCannotRun":
        return "容器启动失败：请检查镜像和启动命令是否正确。"
    if exit_code == 137:
        return "进程被终止 (SIGKILL)：可能是内存不足。建议增加内存或检查训练脚本。"
    if exit_code == 1:
        return "训练脚本执行错误：请查看日志获取详细错误信息。"
    if exit_code != 0:
        return f"训练异常退出 (退出码: {exit_code})：请查看日志获取详细信息。"
    return f"训练任务失败 (原因: {reason})：请查看日志获取详细信息。"


async def resolve_pod_failure_reason(namespace: str, vcjob_name: str | None) -> str:
    """Best-effort extraction of a human-readable failure reason from a VCJob's pods.

    Returns a generic message when pods are gone or no termination detail is
    available — never raises, so it is safe to call while building a DB error row.
    """
    if not vcjob_name:
        return "训练任务已失败"

    try:
        pods = await list_vcjob_pods(namespace, vcjob_name)
    except Exception:
        return "训练任务已失败，但失败详情不可用（无法查询 Pod 信息）。"

    if not pods:
        return "训练任务已失败，但失败详情不可用（任务资源已被清理）。"

    for pod_info in pods:
        try:
            failure = await get_pod_failure_info(namespace, pod_info["pod_name"])
        except Exception:
            continue
        if failure:
            return map_failure_message(failure)

    return "训练任务已失败，但未能获取具体失败原因。"
