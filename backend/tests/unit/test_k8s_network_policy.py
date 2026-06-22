from unittest.mock import AsyncMock, MagicMock, patch

from app.integrations.k8s.network_policy import (
    POLICY_NAME,
    build_tenant_network_policy,
    create_tenant_network_policy,
    delete_network_policy,
    get_allowed_namespaces,
)


class TestBuildTenantNetworkPolicy:
    def test_policy_metadata(self):
        policy = build_tenant_network_policy("kubeai-test-123")
        assert policy.metadata.name == POLICY_NAME
        assert policy.metadata.namespace == "kubeai-test-123"

    def test_policy_types(self):
        policy = build_tenant_network_policy("kubeai-test-123")
        assert set(policy.spec.policy_types) == {"Ingress", "Egress"}

    def test_ingress_rules(self):
        policy = build_tenant_network_policy("kubeai-test-123")
        assert len(policy.spec.ingress) == 1
        ingress_from = policy.spec.ingress[0]._from
        assert len(ingress_from) == 1 + len(get_allowed_namespaces())

    def test_egress_rules_count(self):
        policy = build_tenant_network_policy("kubeai-test-123")
        assert len(policy.spec.egress) == 3

    def test_egress_rules_allow_namespace_traffic(self):
        policy = build_tenant_network_policy("kubeai-test-123")
        egress_to = policy.spec.egress[0].to
        assert len(egress_to) == 1 + len(get_allowed_namespaces())
        egress_to = policy.spec.egress[0].to
        assert len(egress_to) == 1 + len(get_allowed_namespaces())

    def test_allows_platform_namespace(self):
        policy = build_tenant_network_policy("kubeai-test-123")
        ingress_from = policy.spec.ingress[0]._from
        namespace_names = {peer.namespace_selector.match_labels["kubernetes.io/metadata.name"] for peer in ingress_from}
        assert "kubeai" in namespace_names

    def test_egress_rules_allow_dns(self):
        policy = build_tenant_network_policy("kubeai-test-123")
        dns_egress = policy.spec.egress[1]
        assert len(dns_egress.to) == 1
        assert dns_egress.to[0].ip_block.cidr == "0.0.0.0/0"
        ports = dns_egress.ports
        assert any(p.protocol == "TCP" and p.port == 53 for p in ports)
        assert any(p.protocol == "UDP" and p.port == 53 for p in ports)

    def test_egress_rules_allow_http_https_ssh(self):
        policy = build_tenant_network_policy("kubeai-test-123")
        internet_egress = policy.spec.egress[2]
        assert len(internet_egress.to) == 1
        assert internet_egress.to[0].ip_block.cidr == "0.0.0.0/0"
        ports = internet_egress.ports
        port_set = {(p.protocol, p.port) for p in ports}
        assert ("TCP", 80) in port_set
        assert ("TCP", 443) in port_set
        assert ("TCP", 22) in port_set
        assert len(ports) == 3


class TestCreateTenantNetworkPolicy:
    @patch("app.integrations.k8s.network_policy.get_k8s_clients", new_callable=AsyncMock)
    async def test_create_success(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.create_namespaced_network_policy = AsyncMock()
        mock_get_clients.return_value = {"networking_v1": mock_api}

        await create_tenant_network_policy("kubeai-test-123")
        mock_api.create_namespaced_network_policy.assert_called_once()

    @patch("app.integrations.k8s.network_policy.get_k8s_clients", new_callable=AsyncMock)
    async def test_create_already_exists_replaces(self, mock_get_clients):
        from kubernetes_asyncio.client.rest import ApiException

        mock_api = MagicMock()
        mock_api.create_namespaced_network_policy = AsyncMock(side_effect=ApiException(status=409))
        mock_api.replace_namespaced_network_policy = AsyncMock()
        mock_get_clients.return_value = {"networking_v1": mock_api}

        await create_tenant_network_policy("kubeai-test-123")

        mock_api.replace_namespaced_network_policy.assert_called_once()


class TestDeleteNetworkPolicy:
    @patch("app.integrations.k8s.network_policy.get_k8s_clients", new_callable=AsyncMock)
    async def test_delete_success(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.delete_namespaced_network_policy = AsyncMock()
        mock_get_clients.return_value = {"networking_v1": mock_api}

        await delete_network_policy("kubeai-test-123")
        mock_api.delete_namespaced_network_policy.assert_called_once()

    @patch("app.integrations.k8s.network_policy.get_k8s_clients", new_callable=AsyncMock)
    async def test_delete_not_found(self, mock_get_clients):
        from kubernetes_asyncio.client.rest import ApiException

        mock_api = MagicMock()
        mock_api.delete_namespaced_network_policy = AsyncMock(side_effect=ApiException(status=404))
        mock_get_clients.return_value = {"networking_v1": mock_api}

        await delete_network_policy("kubeai-test-123")
