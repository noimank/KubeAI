from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx

from app.integrations.jupyterhub.client import JupyterHubClient, close_jupyterhub_client, get_jupyterhub_client
from app.models.enums import DevEnvironmentStatus


def _make_response(
    method: str, url: str, status_code: int = 200, json_data: dict[str, Any] | None = None
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={} if json_data is None else json_data,
        request=httpx.Request(method, url),
    )


class TestJupyterHubClient:
    async def test_reuses_async_client_with_base_url_and_headers(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api/", token="test-token")

        first = client._get_client()
        second = client._get_client()

        request = first.build_request("GET", "users/alice")
        assert first is second
        assert str(request.url) == "http://jupyterhub/hub/api/users/alice"
        assert request.headers["authorization"] == "token test-token"
        assert request.headers["content-type"] == "application/json"

        await client.close()
        assert first.is_closed

    async def test_get_client_reopens_after_close(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")

        first = client._get_client()
        await client.close()
        second = client._get_client()

        assert first is not second
        assert not second.is_closed
        await client.close()

    async def test_get_user_returns_none_on_404(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.get.return_value = _make_response("GET", "http://jupyterhub/hub/api/users/missing", 404)

        with patch.object(client, "_get_client", return_value=mock_http):
            user = await client.get_user("missing")

        assert user is None
        mock_http.get.assert_awaited_once_with("users/missing")

    async def test_ensure_user_handles_409_as_idempotent(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice",
            409,
            json_data={"name": "alice"},
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.ensure_user("alice")

        assert result == {"name": "alice"}
        mock_http.post.assert_awaited_once_with("users/alice")

    async def test_start_server_sends_kubespawner_override(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            202,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.start_server(
                "alice",
                image="jupyter/pytorch:latest",
                gpu_count=1,
                namespace="kubeai-default",
            )

        assert result == {"status": "starting"}
        mock_http.post.assert_awaited_once_with(
            "users/alice/server",
            json={
                "kubespawner_override": {
                    "resources": {
                        "requests": {"cpu": "2", "memory": "4Gi", "nvidia.com/gpu": "1"},
                        "limits": {"cpu": "2", "memory": "4Gi", "nvidia.com/gpu": "1"},
                    },
                    "image": "jupyter/pytorch:latest",
                    "namespace": "kubeai-default",
                }
            },
        )

    async def test_start_server_rstudio_uses_jupyterhub_singleuser_with_proxy(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            202,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.start_server(
                "alice",
                image="rocker/rstudio:latest",
                environment_type="rstudio",
                env_vars={
                    "KUBEAI_ROOT_PATH": "/kubeai",
                    "KUBEAI_HOME_PATH": "/kubeai/home",
                    "KUBEAI_WORKSPACE_PATH": "/kubeai/workspace",
                },
                extra_volumes=[
                    {"name": "home-volume", "hostPath": {"path": "/data/kubeai/users/alice"}},
                    {"name": "workspace-volume", "hostPath": {"path": "/data/kubeai/tenant/default/workspace"}},
                ],
                extra_volume_mounts=[
                    {"name": "home-volume", "mountPath": "/kubeai/home"},
                    {"name": "workspace-volume", "mountPath": "/kubeai/workspace"},
                ],
            )

        assert result == {"status": "starting"}
        call_kwargs = mock_http.post.call_args[1]
        override = call_kwargs["json"]["kubespawner_override"]
        assert override["cmd"] == ["jupyterhub-singleuser"]
        assert override["defaultUrl"] == "/rstudio/"
        assert override["workingDir"] == "/kubeai"
        assert override["args"] == [
            "--ServerApp.default_url=/rstudio/",
            "--ServerApp.root_dir=/kubeai",
            "--ServerApp.preferred_dir=/kubeai",
        ]
        assert {"name": "HOME", "value": "/kubeai/home"} in override["env"]
        assert override["initContainers"][0]["name"] == "prepare-jupyter-storage"

    async def test_start_server_jupyter_uses_singleuser_command(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            202,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.start_server("alice", environment_type="jupyter")

        assert result == {"status": "starting"}
        call_kwargs = mock_http.post.call_args[1]
        override = call_kwargs["json"]["kubespawner_override"]
        assert override["cmd"] == ["jupyterhub-singleuser"]
        assert override["defaultUrl"] == "/lab"
        assert override["workingDir"] == "/kubeai"
        assert "env" not in override

    async def test_start_server_jupyter_uses_user_home_as_lab_root(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            202,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.start_server(
                "alice",
                image="jupyter/scipy:latest",
                environment_type="jupyter",
                env_vars={
                    "KUBEAI_ROOT_PATH": "/kubeai",
                    "KUBEAI_HOME_PATH": "/kubeai/home",
                    "KUBEAI_WORKSPACE_PATH": "/kubeai/workspace",
                },
                extra_volumes=[
                    {"name": "home-volume", "hostPath": {"path": "/data/kubeai/users/alice"}},
                    {"name": "workspace-volume", "hostPath": {"path": "/data/kubeai/tenant/default/workspace"}},
                ],
                extra_volume_mounts=[
                    {"name": "home-volume", "mountPath": "/kubeai/home"},
                    {"name": "workspace-volume", "mountPath": "/kubeai/workspace"},
                ],
            )

        assert result == {"status": "starting"}
        call_kwargs = mock_http.post.call_args[1]
        override = call_kwargs["json"]["kubespawner_override"]
        assert override["workingDir"] == "/kubeai"
        assert override["args"] == [
            "--ServerApp.root_dir=/kubeai",
            "--ServerApp.preferred_dir=/kubeai",
        ]
        assert {"name": "HOME", "value": "/kubeai/home"} in override["env"]
        assert override["initContainers"] == [
            {
                "name": "prepare-jupyter-storage",
                "image": "jupyter/scipy:latest",
                "command": ["sh", "-c"],
                "args": [
                    "mkdir -p '/kubeai/home' '/kubeai/workspace' "
                    "&& chown -R 1000:100 '/kubeai/home' '/kubeai/workspace'"
                ],
                "resources": {
                    "requests": {"cpu": "10m", "memory": "16Mi"},
                    "limits": {"cpu": "50m", "memory": "64Mi"},
                },
                "securityContext": {"runAsUser": 0, "runAsNonRoot": False},
                "volumeMounts": [
                    {"name": "home-volume", "mountPath": "/kubeai/home"},
                    {"name": "workspace-volume", "mountPath": "/kubeai/workspace"},
                ],
            }
        ]

    async def test_start_server_vscode_uses_jupyterhub_singleuser_with_proxy(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            202,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.start_server(
                "alice",
                image="hub.example.com/kubeai/vscode-base:latest",
                environment_type="vscode",
                env_vars={
                    "KUBEAI_ROOT_PATH": "/kubeai",
                    "KUBEAI_HOME_PATH": "/kubeai/home",
                    "KUBEAI_WORKSPACE_PATH": "/kubeai/workspace",
                },
                extra_volumes=[
                    {"name": "home-volume", "hostPath": {"path": "/data/kubeai/users/alice"}},
                    {"name": "workspace-volume", "hostPath": {"path": "/data/kubeai/tenant/default/workspace"}},
                ],
                extra_volume_mounts=[
                    {"name": "home-volume", "mountPath": "/kubeai/home"},
                    {"name": "workspace-volume", "mountPath": "/kubeai/workspace"},
                ],
            )

        assert result == {"status": "starting"}
        call_kwargs = mock_http.post.call_args[1]
        override = call_kwargs["json"]["kubespawner_override"]
        assert override["cmd"] == ["jupyterhub-singleuser"]
        assert override["defaultUrl"] == "/codeserver/"
        assert override["workingDir"] == "/kubeai"
        assert override["args"] == [
            "--ServerApp.default_url=/codeserver/",
            "--ServerApp.root_dir=/kubeai",
            "--ServerApp.preferred_dir=/kubeai",
        ]
        assert {"name": "CODE_SERVER_WORKDIR", "value": "/kubeai"} in override["env"]
        assert {"name": "HOME", "value": "/kubeai/home"} in override["env"]
        assert override["initContainers"][0]["name"] == "prepare-jupyter-storage"
        assert override["initContainers"][0]["resources"]["requests"] == {"cpu": "10m", "memory": "16Mi"}

    async def test_start_server_rstudio_merges_with_existing_env_vars(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            202,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.start_server(
                "alice",
                image="rocker/rstudio:latest",
                environment_type="rstudio",
                env_vars={"FOO": "bar"},
            )

        assert result == {"status": "starting"}
        call_kwargs = mock_http.post.call_args[1]
        override = call_kwargs["json"]["kubespawner_override"]
        env_pairs = override["env"]
        assert {"name": "FOO", "value": "bar"} in env_pairs
        assert override["cmd"] == ["jupyterhub-singleuser"]
        assert override["defaultUrl"] == "/rstudio/"

    async def test_start_server_handles_400_already_running(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            400,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.start_server("alice")

        assert result == {"status": "already_running"}

    async def test_start_server_includes_image_pull_secret(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            202,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.start_server(
                "alice",
                image="hub.example.com/jupyter:latest",
                image_pull_secret="harbor-registry-secret",
            )

        assert result == {"status": "starting"}
        call_kwargs = mock_http.post.call_args[1]
        override = call_kwargs["json"]["kubespawner_override"]
        assert override["imagePullSecret"] == "harbor-registry-secret"

    async def test_start_server_omits_image_pull_secret_when_empty(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        mock_http = AsyncMock()
        mock_http.post.return_value = _make_response(
            "POST",
            "http://jupyterhub/hub/api/users/alice/server",
            202,
        )

        with patch.object(client, "_get_client", return_value=mock_http):
            await client.start_server("alice", image="jupyter:latest")

        call_kwargs = mock_http.post.call_args[1]
        override = call_kwargs["json"]["kubespawner_override"]
        assert "imagePullSecret" not in override

    async def test_close_singleton_resets_cached_client(self) -> None:
        singleton = get_jupyterhub_client()
        await close_jupyterhub_client()

        assert get_jupyterhub_client() is not singleton
        await close_jupyterhub_client()


class TestMapServerStatus:
    def test_none_returns_stopped(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        assert client.map_server_status(None) == DevEnvironmentStatus.STOPPED

    def test_ready_true_returns_running(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        assert client.map_server_status({"ready": True}) == DevEnvironmentStatus.RUNNING

    def test_pending_spawn_returns_creating(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        assert client.map_server_status({"pending": "spawn", "ready": False}) == DevEnvironmentStatus.CREATING

    def test_pending_stopping_returns_creating(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        assert client.map_server_status({"pending": "stopping", "ready": False}) == DevEnvironmentStatus.CREATING

    def test_empty_server_returns_creating(self) -> None:
        client = JupyterHubClient(base_url="http://jupyterhub/hub/api", token="test-token")
        assert client.map_server_status({}) == DevEnvironmentStatus.CREATING
