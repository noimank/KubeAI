import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.monitoring_service import MonitoringService, _empty_overview, _pct


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return MonitoringService(mock_db)


def _make_tenant(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "name": "test-tenant",
        "display_name": "测试租户",
        "gpu_limit": 4,
        "cpu_limit": "8",
        "memory_limit": "16Gi",
        "storage_limit": "100Gi",
        "k8s_namespace_name": "kubeai-test-tenant",
    }
    defaults.update(overrides)
    tenant = MagicMock()
    for k, v in defaults.items():
        setattr(tenant, k, v)
    return tenant


class TestPct:
    def test_normal(self):
        assert _pct(5, 10) == 50.0

    def test_zero_total(self):
        assert _pct(5, 0) == 0.0

    def test_rounding(self):
        assert _pct(1, 3) == 33.3


class TestEmptyOverview:
    def test_structure(self):
        overview = _empty_overview()
        assert overview["gpu"]["total"] == 0
        assert overview["cpu"]["utilization"] == 0.0
        assert overview["storage"]["used"] == 0


class TestGetClusterOverview:
    @pytest.mark.asyncio
    @patch("app.services.monitoring_service.get_cluster_capacity")
    @patch("app.services.monitoring_service.get_cluster_usage")
    async def test_returns_overview(self, mock_usage, mock_capacity, service):
        mock_capacity.return_value = {"gpu": "8", "cpu": "32", "memory": "131072Ki"}
        mock_usage.return_value = {"gpu": "3", "cpu": "16", "memory": "65536Ki", "storage": "50000Ki"}

        result = await service.get_cluster_overview()

        assert result["gpu"]["total"] == 8
        assert result["gpu"]["used"] == 3
        assert result["gpu"]["utilization"] == 37.5
        assert result["cpu"]["total"] == 32
        assert result["cpu"]["used"] == 16

    @pytest.mark.asyncio
    @patch("app.services.monitoring_service.get_cluster_capacity", side_effect=Exception("k8s down"))
    async def test_graceful_degradation(self, mock_capacity, service):
        result = await service.get_cluster_overview()
        assert result == _empty_overview()


class TestGetNodeDetails:
    @pytest.mark.asyncio
    @patch("app.services.monitoring_service.get_node_resource_details")
    async def test_returns_nodes(self, mock_nodes, service):
        mock_nodes.return_value = [{"name": "node-1", "gpu": {"allocatable": 4, "allocated": 2}}]
        result = await service.get_node_details()
        assert len(result) == 1
        assert result[0]["name"] == "node-1"

    @pytest.mark.asyncio
    @patch("app.services.monitoring_service.get_node_resource_details", side_effect=Exception("fail"))
    async def test_graceful_degradation(self, mock_nodes, service):
        result = await service.get_node_details()
        assert result == []


class TestGetTenantResourceSummary:
    @pytest.mark.asyncio
    @patch("app.services.monitoring_service.get_all_tenants_usage")
    async def test_returns_summary(self, mock_usage, service):
        tenant = _make_tenant()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tenant]

        count_result = MagicMock()
        count_result.scalar.return_value = 3

        service.db.execute = AsyncMock(side_effect=[mock_result, count_result, count_result])

        mock_usage.return_value = [
            {
                "namespace": "kubeai-test-tenant",
                "quota": {"gpu": 4, "cpu": "8", "memory": "16Gi", "storage": "100Gi"},
                "used": {"gpu": 2, "cpu": "4", "memory": "8Gi", "storage": "50Gi"},
            }
        ]

        result = await service.get_tenant_resource_summary()
        assert len(result) == 1
        assert result[0]["tenant_name"] == "测试租户"
        assert result[0]["active_jobs_count"] == 3

    @pytest.mark.asyncio
    @patch("app.services.monitoring_service.get_all_tenants_usage", side_effect=Exception("fail"))
    async def test_graceful_degradation(self, mock_usage, service):
        tenant = _make_tenant()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tenant]
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        service.db.execute = AsyncMock(side_effect=[mock_result, count_result, count_result])

        result = await service.get_tenant_resource_summary()
        assert len(result) == 1


class TestGetTenantResourceDetail:
    @pytest.mark.asyncio
    @patch("app.services.monitoring_service.get_all_tenants_usage")
    async def test_returns_detail(self, mock_usage, service):
        tenant = _make_tenant()
        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = tenant

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        count_result.scalars.return_value.all.return_value = []

        service.db.execute = AsyncMock(side_effect=[tenant_result, count_result, count_result])

        mock_usage.return_value = [
            {
                "namespace": "kubeai-test-tenant",
                "quota": {"gpu": 4, "cpu": "8", "memory": "16Gi", "storage": "100Gi"},
                "used": {"gpu": 2, "cpu": "4", "memory": "8Gi", "storage": "50Gi"},
            }
        ]

        result = await service.get_tenant_resource_detail(tenant.id)
        assert result is not None
        assert result["tenant_name"] == "测试租户"
        assert result["gpu"]["used"] == 2

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, service):
        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=tenant_result)

        result = await service.get_tenant_resource_detail(uuid.uuid4())
        assert result is None
