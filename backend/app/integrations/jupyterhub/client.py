from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from app.core.config import settings
from app.models.enums import DevEnvironmentStatus

logger = logging.getLogger(__name__)


class JupyterHubClient:
    def __init__(self) -> None:
        self._base_url = settings.JUPYTERHUB_API_URL
        self._token = settings.JUPYTERHUB_API_TOKEN

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self._token}", "Content-Type": "application/json"}

    async def ensure_user(self, username: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/users/{username}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return cast("dict[str, Any]", resp.json())

    async def get_user(self, username: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/users/{username}",
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return cast("dict[str, Any]", resp.json())

    async def start_server(
        self,
        username: str,
        *,
        image: str = "",
        cpu: str = "2",
        memory: str = "4Gi",
        gpu_count: int = 0,
        pvc_name: str | None = None,
        extra_volumes: list[dict[str, Any]] | None = None,
        extra_volume_mounts: list[dict[str, Any]] | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        k8s: dict[str, Any] = {}

        resource_requests: dict[str, Any] = {"cpu": cpu, "memory": memory}
        resource_limits: dict[str, Any] = {"cpu": cpu, "memory": memory}
        if gpu_count > 0:
            resource_requests["nvidia.com/gpu"] = str(gpu_count)
            resource_limits["nvidia.com/gpu"] = str(gpu_count)

        k8s["resources"] = {
            "requests": resource_requests,
            "limits": resource_limits,
        }

        if image:
            k8s["image"] = image

        volumes: list[dict[str, Any]] = []
        volume_mounts: list[dict[str, Any]] = []
        if pvc_name:
            volumes.append({"name": "workspace", "persistentVolumeClaim": {"claimName": pvc_name}})
            volume_mounts.append({"name": "workspace", "mountPath": "/home/jovyan/work"})

        if extra_volumes:
            volumes.extend(extra_volumes)
        if extra_volume_mounts:
            volume_mounts.extend(extra_volume_mounts)

        if volumes:
            k8s["volumes"] = volumes
        if volume_mounts:
            k8s["volumeMounts"] = volume_mounts

        if env_vars:
            k8s["env"] = [{"name": k, "value": v} for k, v in env_vars.items()]

        if k8s:
            body["kubespawner_override"] = k8s

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/users/{username}/server",
                headers=self._headers(),
                json=body,
            )
            if resp.status_code == 202:
                return {"status": "starting"}
            if resp.status_code == 201:
                return {"status": "already_running"}
            resp.raise_for_status()
            return cast("dict[str, Any]", resp.json())

    async def stop_server(self, username: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self._base_url}/users/{username}/server",
                headers=self._headers(),
            )
            if resp.status_code == 202:
                return {"status": "stopping"}
            if resp.status_code == 204:
                return {"status": "stopped"}
            resp.raise_for_status()
            return cast("dict[str, Any]", resp.json())

    async def delete_user(self, username: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self._base_url}/users/{username}",
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return
            resp.raise_for_status()

    def map_server_status(self, server: dict[str, Any] | None) -> DevEnvironmentStatus:
        if server is None:
            return DevEnvironmentStatus.STOPPED

        phase = server.get("pending", None)
        ready = server.get("ready", False)

        if ready:
            return DevEnvironmentStatus.RUNNING
        if phase in ("spawn", "stopping"):
            return DevEnvironmentStatus.CREATING
        if phase == "ready":
            return DevEnvironmentStatus.RUNNING
        return DevEnvironmentStatus.CREATING


_jupyterhub_client: JupyterHubClient | None = None


def get_jupyterhub_client() -> JupyterHubClient:
    global _jupyterhub_client
    if _jupyterhub_client is None:
        _jupyterhub_client = JupyterHubClient()
    return _jupyterhub_client
