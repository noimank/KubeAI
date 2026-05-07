from unittest.mock import MagicMock, patch

import pytest
import requests  # type: ignore[import-untyped]

from app.integrations.harbor.client import HarborClient


@pytest.fixture
def harbor():
    with patch("app.integrations.harbor.client.settings") as mock_settings:
        mock_settings.HARBOR_URL = "http://harbor.kubeai.local"
        mock_settings.HARBOR_USERNAME = "admin"
        mock_settings.HARBOR_PASSWORD = "Harbor12345"
        mock_settings.HARBOR_PROJECT_PREFIX = "kubeai-"
        return HarborClient()


class TestHealthCheck:
    @patch("app.integrations.harbor.client.requests.get")
    def test_health_check_ok(self, mock_get, harbor):
        mock_get.return_value = MagicMock(status_code=200)
        assert harbor.health_check() is True
        mock_get.assert_called_once()

    @patch("app.integrations.harbor.client.requests.get")
    def test_health_check_fail(self, mock_get, harbor):
        mock_get.side_effect = requests.RequestException("connection error")
        assert harbor.health_check() is False


class TestGetProject:
    @patch("app.integrations.harbor.client.requests.get")
    def test_get_project_found(self, mock_get, harbor):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"name": "kubeai-test", "project_id": 1}],
        )
        result = harbor.get_project("kubeai-test")
        assert result is not None
        assert result["name"] == "kubeai-test"

    @patch("app.integrations.harbor.client.requests.get")
    def test_get_project_not_found(self, mock_get, harbor):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        result = harbor.get_project("kubeai-missing")
        assert result is None


class TestEnsureProject:
    @patch.object(HarborClient, "get_project")
    def test_ensure_project_already_exists(self, mock_get, harbor):
        mock_get.return_value = {"name": "kubeai-test", "project_id": 1}
        result = harbor.ensure_project("kubeai-test")
        assert result["name"] == "kubeai-test"

    @patch("app.integrations.harbor.client.requests.post")
    @patch.object(HarborClient, "get_project")
    def test_ensure_project_create_new(self, mock_get, mock_post, harbor):
        mock_get.side_effect = [
            None,
            {"name": "kubeai-new", "project_id": 2},
        ]
        mock_post.return_value = MagicMock(status_code=201)
        result = harbor.ensure_project("kubeai-new")
        assert result["name"] == "kubeai-new"
        mock_post.assert_called_once()


class TestMakeHarborImageRef:
    def test_make_ref(self, harbor):
        ref = harbor.make_harbor_image_ref("test-tenant", "my-image", "v1.0")
        assert ref == "harbor.kubeai.local/kubeai-test-tenant/my-image:v1.0"


class TestMakeHarborDockerconfig:
    def test_dockerconfig(self, harbor):
        config = harbor.make_harbor_dockerconfig()
        assert ".dockerconfigjson" in config
        import json

        parsed = json.loads(config[".dockerconfigjson"])
        assert "auths" in parsed
        assert "harbor.kubeai.local" in parsed["auths"]
