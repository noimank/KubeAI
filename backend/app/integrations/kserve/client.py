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
