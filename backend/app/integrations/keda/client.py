import logging
from typing import Any, cast

from kubernetes_asyncio.client.exceptions import ApiException

from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

KEDA_GROUP = "keda.sh"
KEDA_VERSION = "v1alpha1"
KEDA_PLURAL = "scaledobjects"


async def create_scaled_object(namespace: str, body: dict[str, Any]) -> dict[str, Any]:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    return cast(
        "dict[str, Any]",
        await api.create_namespaced_custom_object(
            group=KEDA_GROUP,
            version=KEDA_VERSION,
            namespace=namespace,
            plural=KEDA_PLURAL,
            body=body,
        ),
    )


async def get_scaled_object(namespace: str, name: str) -> dict[str, Any] | None:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        return cast(
            "dict[str, Any]",
            await api.get_namespaced_custom_object(
                group=KEDA_GROUP,
                version=KEDA_VERSION,
                namespace=namespace,
                plural=KEDA_PLURAL,
                name=name,
            ),
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def delete_scaled_object(namespace: str, name: str) -> None:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    try:
        await api.delete_namespaced_custom_object(
            group=KEDA_GROUP,
            version=KEDA_VERSION,
            namespace=namespace,
            plural=KEDA_PLURAL,
            name=name,
            body={"propagationPolicy": "Background"},
        )
    except ApiException as e:
        if e.status == 404:
            logger.info("ScaledObject %s not found in %s, ignoring delete", name, namespace)
            return
        raise


async def patch_scaled_object(namespace: str, name: str, body: dict[str, Any]) -> dict[str, Any]:
    k8s = await get_k8s_clients()
    api = k8s["custom_objects"]
    return cast(
        "dict[str, Any]",
        await api.patch_namespaced_custom_object(
            group=KEDA_GROUP,
            version=KEDA_VERSION,
            namespace=namespace,
            plural=KEDA_PLURAL,
            name=name,
            body=body,
        ),
    )
