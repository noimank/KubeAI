from __future__ import annotations

import json
import logging
from typing import Any, cast

from kubernetes_asyncio.client.exceptions import ApiException

from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

MANAGED_BY_LABEL = "kubeai"


def build_deployment(
    *,
    name: str,
    namespace: str,
    image: str,
    container_port: int,
    command: list[str] | None = None,
    args: list[str] | None = None,
    replicas: int = 1,
    resources: dict[str, Any] | None = None,
    env_vars: dict[str, str] | None = None,
) -> dict[str, Any]:
    labels = {"app.kubernetes.io/name": name, "app.kubernetes.io/managed-by": MANAGED_BY_LABEL}

    container: dict[str, Any] = {
        "name": name,
        "image": image,
        "ports": [{"containerPort": container_port}],
    }
    if command:
        container["command"] = command
    if args:
        container["args"] = args
    if resources:
        container["resources"] = resources
    if env_vars:
        container["env"] = [{"name": k, "value": v} for k, v in env_vars.items()]

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {"containers": [container]},
            },
        },
    }


def build_service(
    *,
    name: str,
    namespace: str,
    target_port: int,
    deployment_name: str,
) -> dict[str, Any]:
    labels = {"app.kubernetes.io/name": deployment_name, "app.kubernetes.io/managed-by": MANAGED_BY_LABEL}
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "type": "ClusterIP",
            "selector": labels,
            "ports": [{"port": target_port, "targetPort": target_port, "protocol": "TCP"}],
        },
    }


def parse_json_field(value: str | None) -> list[str] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


# ── Deployment CRUD ─────────────────────────────────────────────────────


async def create_deployment(namespace: str, body: dict[str, Any]) -> dict[str, Any]:
    k8s = await get_k8s_clients()
    api = k8s["apps_v1"]
    try:
        resp = await api.create_namespaced_deployment(namespace=namespace, body=body)
        return cast("dict[str, Any]", resp.to_dict())
    except ApiException as e:
        if e.status == 409:
            logger.info("Deployment %s already exists in %s, ignoring", body["metadata"]["name"], namespace)
            existing = await get_deployment(namespace, body["metadata"]["name"])
            return existing or {}
        raise


async def get_deployment(namespace: str, name: str) -> dict[str, Any] | None:
    k8s = await get_k8s_clients()
    api = k8s["apps_v1"]
    try:
        resp = await api.read_namespaced_deployment(name=name, namespace=namespace)
        return cast("dict[str, Any]", resp.to_dict())
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def patch_deployment(namespace: str, name: str, body: dict[str, Any]) -> dict[str, Any]:
    k8s = await get_k8s_clients()
    api = k8s["apps_v1"]
    resp = await api.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
    return cast("dict[str, Any]", resp.to_dict())


async def delete_deployment(namespace: str, name: str) -> None:
    k8s = await get_k8s_clients()
    api = k8s["apps_v1"]
    try:
        await api.delete_namespaced_deployment(name=name, namespace=namespace, body={"propagationPolicy": "Background"})
    except ApiException as e:
        if e.status == 404:
            logger.info("Deployment %s not found in %s, ignoring delete", name, namespace)
            return
        raise


# ── Service CRUD ─────────────────────────────────────────────────────────


async def create_k8s_service(namespace: str, body: dict[str, Any]) -> dict[str, Any]:
    k8s = await get_k8s_clients()
    api = k8s["core_v1"]
    try:
        resp = await api.create_namespaced_service(namespace=namespace, body=body)
        return cast("dict[str, Any]", resp.to_dict())
    except ApiException as e:
        if e.status == 409:
            logger.info("Service %s already exists in %s, ignoring", body["metadata"]["name"], namespace)
            existing = await get_k8s_service(namespace, body["metadata"]["name"])
            return existing or {}
        raise


async def get_k8s_service(namespace: str, name: str) -> dict[str, Any] | None:
    k8s = await get_k8s_clients()
    api = k8s["core_v1"]
    try:
        resp = await api.read_namespaced_service(name=name, namespace=namespace)
        return cast("dict[str, Any]", resp.to_dict())
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def delete_k8s_service(namespace: str, name: str) -> None:
    k8s = await get_k8s_clients()
    api = k8s["core_v1"]
    try:
        await api.delete_namespaced_service(name=name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            logger.info("Service %s not found in %s, ignoring delete", name, namespace)
            return
        raise


# ── Events ───────────────────────────────────────────────────────────────


async def list_deployment_events(namespace: str, deployment_name: str) -> list[dict[str, Any]]:
    from app.integrations.kserve.client import _event_to_dict

    core_v1 = (await get_k8s_clients())["core_v1"]
    events: list[dict[str, Any]] = []

    try:
        dep_resp = await core_v1.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.kind=Deployment,involvedObject.name={deployment_name}",
        )
        for e in dep_resp.items:
            events.append(_event_to_dict(e))
    except Exception:
        logger.warning("Failed to list Deployment events for %s", deployment_name, exc_info=True)

    try:
        pods_resp = await core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"app.kubernetes.io/name={deployment_name}",
        )
        if pods_resp.items:
            pod_uids = {pod.metadata.uid for pod in pods_resp.items if pod.metadata.uid}
            if pod_uids:
                ns_resp = await core_v1.list_namespaced_event(namespace=namespace, limit=500)
                for e in ns_resp.items:
                    if e.involved_object and e.involved_object.uid in pod_uids:
                        events.append(_event_to_dict(e))
    except Exception:
        logger.warning("Failed to list Pod events for %s", deployment_name, exc_info=True)

    events.sort(key=lambda x: x.get("last_timestamp") or "", reverse=True)
    return events[:100]
