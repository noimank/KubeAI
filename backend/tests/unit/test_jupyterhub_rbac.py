from unittest.mock import AsyncMock, MagicMock, patch

from app.integrations.jupyterhub.rbac import (
    ROLE_BINDING_NAME,
    ROLE_NAME,
    build_jupyterhub_tenant_role,
    build_jupyterhub_tenant_role_binding,
    ensure_jupyterhub_tenant_rbac,
)


class TestJupyterHubTenantRBAC:
    def test_build_role(self):
        role = build_jupyterhub_tenant_role("kubeai-default")

        assert role.metadata.name == ROLE_NAME
        assert role.metadata.namespace == "kubeai-default"
        assert {resource for rule in role.rules for resource in rule.resources} >= {"pods", "persistentvolumeclaims"}

    @patch("app.integrations.jupyterhub.rbac.settings")
    def test_build_role_binding(self, mock_settings):
        mock_settings.JUPYTERHUB_HUB_SERVICE_ACCOUNT = "kubeai-hub"
        mock_settings.K8S_PLATFORM_NAMESPACE = "kubeai"

        role_binding = build_jupyterhub_tenant_role_binding("kubeai-default")

        assert role_binding is not None
        assert role_binding.metadata.name == ROLE_BINDING_NAME
        assert role_binding.subjects[0].name == "kubeai-hub"
        assert role_binding.subjects[0].namespace == "kubeai"
        assert role_binding.role_ref.name == ROLE_NAME

    @patch("app.integrations.jupyterhub.rbac.get_k8s_clients", new_callable=AsyncMock)
    @patch("app.integrations.jupyterhub.rbac.settings")
    async def test_ensure_creates_role_and_binding(self, mock_settings, mock_get_clients):
        mock_settings.JUPYTERHUB_HUB_SERVICE_ACCOUNT = "kubeai-hub"
        mock_settings.K8S_PLATFORM_NAMESPACE = "kubeai"
        mock_api = MagicMock()
        mock_api.create_namespaced_role = AsyncMock()
        mock_api.create_namespaced_role_binding = AsyncMock()
        mock_get_clients.return_value = {"rbac_v1": mock_api}

        await ensure_jupyterhub_tenant_rbac("kubeai-default")

        mock_api.create_namespaced_role.assert_called_once()
        mock_api.create_namespaced_role_binding.assert_called_once()

    @patch("app.integrations.jupyterhub.rbac.get_k8s_clients", new_callable=AsyncMock)
    @patch("app.integrations.jupyterhub.rbac.settings")
    async def test_ensure_skips_when_service_account_not_configured(self, mock_settings, mock_get_clients):
        mock_settings.JUPYTERHUB_HUB_SERVICE_ACCOUNT = ""

        await ensure_jupyterhub_tenant_rbac("kubeai-default")

        mock_get_clients.assert_not_called()
