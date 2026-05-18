from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.harbor.client import HarborClient


@pytest.fixture
def harbor():
    with patch("app.integrations.harbor.client.settings") as mock_settings:
        mock_settings.HARBOR_URL = "http://harbor.kubeai.local"
        mock_settings.HARBOR_USERNAME = "admin"
        mock_settings.HARBOR_PASSWORD = "Harbor12345"
        mock_settings.HARBOR_PROJECT_PREFIX = "kubeai-"
        client = HarborClient()
    return client


class TestHealthCheck:
    async def test_health_check_ok(self, harbor):
        mock_resp = MagicMock(status_code=200)
        harbor._client.get = AsyncMock(return_value=mock_resp)

        assert await harbor.health_check() is True
        harbor._client.get.assert_called_once()

    async def test_health_check_fail(self, harbor):
        harbor._client.get = AsyncMock(side_effect=httpx.HTTPError("connection error"))

        assert await harbor.health_check() is False


class TestGetProject:
    async def test_get_project_found(self, harbor):
        mock_resp = MagicMock(
            status_code=200,
            json=lambda: [{"name": "kubeai-test", "project_id": 1}],
        )
        harbor._client.get = AsyncMock(return_value=mock_resp)

        result = await harbor.get_project("kubeai-test")
        assert result is not None
        assert result["name"] == "kubeai-test"

    async def test_get_project_not_found(self, harbor):
        mock_resp = MagicMock(status_code=200, json=lambda: [])
        harbor._client.get = AsyncMock(return_value=mock_resp)

        result = await harbor.get_project("kubeai-missing")
        assert result is None


class TestEnsureProject:
    async def test_ensure_project_already_exists(self, harbor):
        existing = {"name": "kubeai-test", "project_id": 1}
        harbor.get_project = AsyncMock(return_value=existing)

        result = await harbor.ensure_project("kubeai-test")
        assert result["name"] == "kubeai-test"

    async def test_ensure_project_create_new(self, harbor):
        harbor.get_project = AsyncMock(side_effect=[None, {"name": "kubeai-new", "project_id": 2}])
        mock_resp = MagicMock(status_code=201)
        harbor._client.post = AsyncMock(return_value=mock_resp)

        result = await harbor.ensure_project("kubeai-new")
        assert result["name"] == "kubeai-new"
        harbor._client.post.assert_called_once()


class TestMakeHarborImageRef:
    def test_make_ref(self, harbor):
        ref = harbor.make_harbor_image_ref("test-tenant", "my-image", "v1.0")
        assert ref == "harbor.kubeai.local/kubeai-test-tenant/my-image:v1.0"


class TestMakeHarborDockerconfig:
    def test_dockerconfig(self, harbor):
        config = harbor.make_harbor_dockerconfig()
        assert "config.json" in config
        import json

        parsed = json.loads(config["config.json"])
        assert "auths" in parsed
        assert "harbor.kubeai.local" in parsed["auths"]
