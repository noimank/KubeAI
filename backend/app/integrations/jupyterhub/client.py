from __future__ import annotations

from typing import Any, cast

import httpx
import structlog

from app.core.config import settings
from app.models.enums import DevEnvironmentStatus

logger = structlog.get_logger(__name__)

JUPYTER_UID = 1000
JUPYTER_GID = 100


class JupyterHubClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self._base_url = (base_url or settings.JUPYTERHUB_API_URL).rstrip("/")
        self._token = settings.JUPYTERHUB_API_TOKEN if token is None else token
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self._token}", "Content-Type": "application/json"}

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers(),
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def ensure_user(self, username: str) -> dict[str, Any]:
        client = self._get_client()
        resp = await client.post(f"users/{username}")
        if resp.status_code == 409:
            return cast("dict[str, Any]", resp.json())
        resp.raise_for_status()
        return cast("dict[str, Any]", resp.json())

    async def get_user(self, username: str) -> dict[str, Any] | None:
        client = self._get_client()
        resp = await client.get(f"users/{username}")
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
        environment_type: str | None = None,
        namespace: str | None = None,
        extra_volumes: list[dict[str, Any]] | None = None,
        extra_volume_mounts: list[dict[str, Any]] | None = None,
        env_vars: dict[str, str] | None = None,
        image_pull_secret: str | None = None,
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
        if namespace:
            k8s["namespace"] = namespace
        if image_pull_secret:
            k8s["imagePullSecret"] = image_pull_secret

        env: dict[str, str] = dict(env_vars) if env_vars else {}

        if environment_type == "jupyter":
            k8s["cmd"] = ["jupyterhub-singleuser"]
            k8s["defaultUrl"] = "/lab"
            root_path = env.get("KUBEAI_ROOT_PATH", "/kubeai")
            k8s["workingDir"] = root_path
            home_path = env.get("KUBEAI_HOME_PATH")
            workspace_path = env.get("KUBEAI_WORKSPACE_PATH")
            if home_path:
                env["HOME"] = home_path
                k8s["args"] = [
                    f"--ServerApp.root_dir={root_path}",
                    f"--ServerApp.preferred_dir={root_path}",
                ]
                mount_names = {item.get("name") for item in extra_volume_mounts or [] if isinstance(item, dict)}
                if "home-volume" in mount_names:
                    k8s["initContainers"] = [
                        self._build_jupyter_storage_init_container(
                            image=image,
                            home_path=home_path,
                            workspace_path=workspace_path if "workspace-volume" in mount_names else None,
                        )
                    ]
        elif environment_type == "vscode":
            root_path = env.get("KUBEAI_ROOT_PATH", "/kubeai")
            home_path = env.get("KUBEAI_HOME_PATH")
            workspace_path = env.get("KUBEAI_WORKSPACE_PATH")
            k8s["cmd"] = ["jupyterhub-singleuser"]
            k8s["workingDir"] = root_path
            env["CODE_SERVER_WORKDIR"] = root_path
            k8s["defaultUrl"] = "/codeserver/"
            k8s["args"] = [
                "--ServerApp.default_url=/codeserver/",
                f"--ServerApp.root_dir={root_path}",
                f"--ServerApp.preferred_dir={root_path}",
            ]
            if home_path:
                env["HOME"] = home_path
                mount_names = {item.get("name") for item in extra_volume_mounts or [] if isinstance(item, dict)}
                if "home-volume" in mount_names:
                    k8s["initContainers"] = [
                        self._build_jupyter_storage_init_container(
                            image=image,
                            home_path=home_path,
                            workspace_path=workspace_path if "workspace-volume" in mount_names else None,
                        )
                    ]
        elif environment_type == "rstudio":
            root_path = env.get("KUBEAI_ROOT_PATH", "/kubeai")
            home_path = env.get("KUBEAI_HOME_PATH")
            workspace_path = env.get("KUBEAI_WORKSPACE_PATH")
            k8s["cmd"] = ["jupyterhub-singleuser"]
            k8s["workingDir"] = root_path
            k8s["defaultUrl"] = "/rstudio/"
            k8s["args"] = [
                "--ServerApp.default_url=/rstudio/",
                f"--ServerApp.root_dir={root_path}",
                f"--ServerApp.preferred_dir={root_path}",
            ]
            if home_path:
                env["HOME"] = home_path
                mount_names = {item.get("name") for item in extra_volume_mounts or [] if isinstance(item, dict)}
                if "home-volume" in mount_names:
                    k8s["initContainers"] = [
                        self._build_jupyter_storage_init_container(
                            image=image,
                            home_path=home_path,
                            workspace_path=workspace_path if "workspace-volume" in mount_names else None,
                        )
                    ]

        volumes: list[dict[str, Any]] = []
        volume_mounts: list[dict[str, Any]] = []

        if extra_volumes:
            volumes.extend(extra_volumes)
        if extra_volume_mounts:
            volume_mounts.extend(extra_volume_mounts)

        if volumes:
            k8s["volumes"] = volumes
        if volume_mounts:
            k8s["volumeMounts"] = volume_mounts

        if env:
            k8s["env"] = [{"name": k, "value": v} for k, v in env.items()]

        if k8s:
            body["kubespawner_override"] = k8s

        client = self._get_client()
        resp = await client.post(f"users/{username}/server", json=body)
        if resp.status_code == 202:
            return {"status": "starting"}
        if resp.status_code == 201:
            return {"status": "already_running"}
        if resp.status_code == 400:
            return {"status": "already_running"}
        resp.raise_for_status()
        return cast("dict[str, Any]", resp.json())

    def _build_jupyter_storage_init_container(
        self,
        *,
        image: str,
        home_path: str,
        workspace_path: str | None,
    ) -> dict[str, Any]:
        paths = [home_path]
        volume_mounts = [{"name": "home-volume", "mountPath": home_path}]
        if workspace_path:
            paths.append(workspace_path)
            volume_mounts.append({"name": "workspace-volume", "mountPath": workspace_path})
        quoted_paths = " ".join(f"'{path}'" for path in paths)
        return {
            "name": "prepare-jupyter-storage",
            "image": image or "busybox:1.36",
            "command": ["sh", "-c"],
            "args": [f"mkdir -p {quoted_paths} && chown -R {JUPYTER_UID}:{JUPYTER_GID} {quoted_paths}"],
            "resources": {
                "requests": {"cpu": "10m", "memory": "16Mi"},
                "limits": {"cpu": "50m", "memory": "64Mi"},
            },
            "securityContext": {"runAsUser": 0, "runAsNonRoot": False},
            "volumeMounts": volume_mounts,
        }

    async def stop_server(self, username: str) -> dict[str, Any]:
        client = self._get_client()
        resp = await client.delete(f"users/{username}/server")
        if resp.status_code == 202:
            return {"status": "stopping"}
        if resp.status_code == 204:
            return {"status": "stopped"}
        resp.raise_for_status()
        return cast("dict[str, Any]", resp.json())

    async def get_server_last_activity(self, username: str) -> str | None:
        user_data = await self.get_user(username)
        if not user_data:
            return None
        servers = user_data.get("servers", {})
        default_server = servers.get("", {})
        return cast("str | None", default_server.get("last_activity"))

    async def delete_user(self, username: str) -> None:
        client = self._get_client()
        resp = await client.delete(f"users/{username}")
        if resp.status_code == 404:
            return
        resp.raise_for_status()

    def map_server_status(self, server: dict[str, Any] | None) -> DevEnvironmentStatus:
        if server is None:
            return DevEnvironmentStatus.STOPPED

        if server.get("ready", False):
            return DevEnvironmentStatus.RUNNING

        phase = server.get("pending")
        if phase in ("spawn", "stopping"):
            return DevEnvironmentStatus.CREATING
        return DevEnvironmentStatus.CREATING


_jupyterhub_client: JupyterHubClient | None = None


def get_jupyterhub_client() -> JupyterHubClient:
    global _jupyterhub_client
    if _jupyterhub_client is None:
        _jupyterhub_client = JupyterHubClient()
    return _jupyterhub_client


async def close_jupyterhub_client() -> None:
    global _jupyterhub_client
    if _jupyterhub_client is not None:
        await _jupyterhub_client.close()
        _jupyterhub_client = None
