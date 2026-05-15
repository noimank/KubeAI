import logging
from typing import Any, cast

from kubernetes_asyncio.client.exceptions import ApiException

from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

KSERVE_GROUP = "serving.kserve.io"
KSERVE_VERSION = "v1beta1"
KSERVE_PLURAL = "inferenceservices"


async def create_inferenceservice(namespace: str, body: dict[str, Any]) -> dict[str, Any]:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        return cast(
            "dict[str, Any]",
            await api.create_namespaced_custom_object(
                group=KSERVE_GROUP,
                version=KSERVE_VERSION,
                namespace=namespace,
                plural=KSERVE_PLURAL,
                body=body,
            ),
        )
    except ApiException as e:
        if e.status == 409:
            logger.info(
                "InferenceService %s already exists in %s, ignoring",
                body.get("metadata", {}).get("name"),
                namespace,
            )
            return await get_inferenceservice(namespace, body["metadata"]["name"]) or {}
        raise


async def get_inferenceservice(namespace: str, name: str) -> dict[str, Any] | None:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        return cast(
            "dict[str, Any]",
            await api.get_namespaced_custom_object(
                group=KSERVE_GROUP,
                version=KSERVE_VERSION,
                namespace=namespace,
                plural=KSERVE_PLURAL,
                name=name,
            ),
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def delete_inferenceservice(namespace: str, name: str) -> None:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        await api.delete_namespaced_custom_object(
            group=KSERVE_GROUP,
            version=KSERVE_VERSION,
            namespace=namespace,
            plural=KSERVE_PLURAL,
            name=name,
            body={"propagationPolicy": "Background"},
        )
    except ApiException as e:
        if e.status == 404:
            logger.info("InferenceService %s not found in %s, ignoring delete", name, namespace)
            return
        raise


async def list_inferenceservices(namespace: str) -> list[dict[str, Any]]:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        resp = cast(
            "dict[str, Any]",
            await api.list_namespaced_custom_object(
                group=KSERVE_GROUP,
                version=KSERVE_VERSION,
                namespace=namespace,
                plural=KSERVE_PLURAL,
            ),
        )
        return cast("list[dict[str, Any]]", resp.get("items", []))
    except ApiException as e:
        if e.status == 404:
            return []
        raise


async def patch_inferenceservice(namespace: str, name: str, body: dict[str, Any]) -> dict[str, Any]:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    return cast(
        "dict[str, Any]",
        await api.patch_namespaced_custom_object(
            group=KSERVE_GROUP,
            version=KSERVE_VERSION,
            namespace=namespace,
            plural=KSERVE_PLURAL,
            name=name,
            body=body,
        ),
    )


async def list_inference_service_events(namespace: str, kserve_name: str) -> list[dict[str, Any]]:
    core_v1 = (await get_k8s_clients())["core_v1"]
    events: list[dict[str, Any]] = []

    try:
        # 1. InferenceService CRD level events
        isv_resp = await core_v1.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.kind=InferenceService,involvedObject.name={kserve_name}",
        )
        for e in isv_resp.items:
            events.append(_event_to_dict(e))
    except Exception:
        logger.warning("Failed to list InferenceService events for %s", kserve_name, exc_info=True)

    try:
        # 2. Get associated Pods
        pods_resp = await core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"serving.kserve.io/inferenceservice={kserve_name}",
        )
        if pods_resp.items:
            pod_uids = {pod.metadata.uid for pod in pods_resp.items if pod.metadata.uid}
            if pod_uids:
                ns_resp = await core_v1.list_namespaced_event(namespace=namespace, limit=500)
                for e in ns_resp.items:
                    if e.involved_object and e.involved_object.uid in pod_uids:
                        events.append(_event_to_dict(e))
    except Exception:
        logger.warning("Failed to list Pod events for %s", kserve_name, exc_info=True)

    events.sort(key=lambda x: x.get("last_timestamp") or "", reverse=True)
    return events[:100]


def _event_to_dict(event: Any) -> dict[str, Any]:
    return {
        "type": event.type or "Normal",
        "reason": event.reason or "",
        "message": event.message or "",
        "involved_object_kind": event.involved_object.kind if event.involved_object else "",
        "involved_object_name": event.involved_object.name if event.involved_object else "",
        "count": event.count or 1,
        "first_timestamp": event.first_timestamp.isoformat() if event.first_timestamp else None,
        "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
    }
