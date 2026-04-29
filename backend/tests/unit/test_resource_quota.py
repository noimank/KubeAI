from unittest.mock import MagicMock, patch

from app.integrations.k8s.resource_quota import (
    RESOURCE_QUOTA_NAME,
    build_tenant_resource_quota,
    create_resource_quota,
    delete_resource_quota,
    update_resource_quota,
)


class TestBuildTenantResourceQuota:
    def test_default_values(self):
        quota = build_tenant_resource_quota()
        assert quota.metadata.name == RESOURCE_QUOTA_NAME
        hard = quota.spec.hard
        assert hard["requests.cpu"] == "4"
        assert hard["requests.memory"] == "8Gi"
        assert hard["requests.storage"] == "10Gi"
        assert hard["requests.nvidia.com/gpu"] == "0"

    def test_custom_values(self):
        quota = build_tenant_resource_quota(
            gpu_limit=4,
            cpu_limit="16",
            memory_limit="32Gi",
            storage_limit="100Gi",
        )
        hard = quota.spec.hard
        assert hard["requests.cpu"] == "16"
        assert hard["requests.memory"] == "32Gi"
        assert hard["requests.storage"] == "100Gi"
        assert hard["requests.nvidia.com/gpu"] == "4"

    def test_api_version_and_kind(self):
        quota = build_tenant_resource_quota()
        assert quota.api_version == "v1"
        assert quota.kind == "ResourceQuota"


class TestCreateResourceQuota:
    @patch("app.integrations.k8s.resource_quota.get_k8s_clients")
    def test_create_success(self, mock_get_clients):
        mock_api = MagicMock()
        mock_get_clients.return_value = {"core_v1": mock_api}

        quota = build_tenant_resource_quota()
        result = create_resource_quota("kubeai-test", quota)
        mock_api.create_namespaced_resource_quota.assert_called_once_with(namespace="kubeai-test", body=quota)
        assert result == quota

    @patch("app.integrations.k8s.resource_quota.get_k8s_clients")
    def test_create_already_exists(self, mock_get_clients):
        from kubernetes.client.rest import ApiException

        mock_api = MagicMock()
        mock_api.create_namespaced_resource_quota.side_effect = ApiException(status=409)
        mock_get_clients.return_value = {"core_v1": mock_api}

        quota = build_tenant_resource_quota()
        result = create_resource_quota("kubeai-test", quota)
        assert result == quota


class TestDeleteResourceQuota:
    @patch("app.integrations.k8s.resource_quota.get_k8s_clients")
    def test_delete_success(self, mock_get_clients):
        mock_api = MagicMock()
        mock_get_clients.return_value = {"core_v1": mock_api}

        delete_resource_quota("kubeai-test")
        mock_api.delete_namespaced_resource_quota.assert_called_once()

    @patch("app.integrations.k8s.resource_quota.get_k8s_clients")
    def test_delete_not_found(self, mock_get_clients):
        from kubernetes.client.rest import ApiException

        mock_api = MagicMock()
        mock_api.delete_namespaced_resource_quota.side_effect = ApiException(status=404)
        mock_get_clients.return_value = {"core_v1": mock_api}

        delete_resource_quota("kubeai-test")


class TestUpdateResourceQuota:
    @patch("app.integrations.k8s.resource_quota.get_k8s_clients")
    def test_update_success(self, mock_get_clients):
        mock_api = MagicMock()
        mock_get_clients.return_value = {"core_v1": mock_api}

        result = update_resource_quota("kubeai-test", gpu_limit=8, cpu_limit="32")
        mock_api.replace_namespaced_resource_quota.assert_called_once()
        assert result.spec.hard["requests.nvidia.com/gpu"] == "8"
        assert result.spec.hard["requests.cpu"] == "32"
