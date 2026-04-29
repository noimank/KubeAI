import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, ExternalServiceException
from app.models.enums import TenantStatus
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreateRequest
from app.services.tenant_service import TenantService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _sync_result_one(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _make_tenant(name="test-tenant"):
    t = Tenant(name=name, display_name=name, description=None)
    t.id = uuid.uuid4()
    t.status = TenantStatus.ACTIVE
    t.gpu_limit = 0
    t.cpu_limit = "4"
    t.memory_limit = "8Gi"
    t.storage_limit = "10Gi"
    return t


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def tenant_service(mock_db):
    return TenantService(mock_db)


class TestCreateTenant:
    @patch("app.services.tenant_service.create_tenant_network_policy")
    @patch("app.services.tenant_service.create_resource_quota")
    @patch("app.services.tenant_service.build_tenant_resource_quota")
    @patch("app.services.tenant_service.create_namespace")
    async def test_create_tenant_success(
        self,
        mock_create_ns,
        mock_build_quota,
        mock_create_quota,
        mock_create_np,
        tenant_service,
        mock_db,
    ):
        mock_db.execute.return_value = _sync_result(None)
        mock_build_quota.return_value = MagicMock()

        result = await tenant_service.create_tenant(
            TenantCreateRequest(name="test", display_name="Test"),
        )

        assert result.name == "test"
        assert result.display_name == "Test"
        assert result.k8s_namespace_name == f"kubeai-{result.id}"
        mock_create_ns.assert_called_once()
        mock_create_quota.assert_called_once()
        mock_create_np.assert_called_once()

    async def test_create_tenant_duplicate_name(self, tenant_service, mock_db):
        existing = _make_tenant()
        mock_db.execute.return_value = _sync_result(existing)

        with pytest.raises(ConflictException, match="租户名称已存在"):
            await tenant_service.create_tenant(
                TenantCreateRequest(name="test-tenant", display_name="Test"),
            )

    @patch("app.services.tenant_service.delete_network_policy")
    @patch("app.services.tenant_service.delete_resource_quota")
    @patch("app.services.tenant_service.delete_namespace")
    @patch("app.services.tenant_service.create_tenant_network_policy")
    @patch("app.services.tenant_service.create_resource_quota")
    @patch("app.services.tenant_service.build_tenant_resource_quota")
    @patch("app.services.tenant_service.create_namespace")
    async def test_create_tenant_k8s_quota_failure_rollback(
        self,
        mock_create_ns,
        mock_build_quota,
        mock_create_quota,
        mock_create_np,
        mock_delete_ns,
        mock_delete_quota,
        mock_delete_np,
        tenant_service,
        mock_db,
    ):
        mock_db.execute.return_value = _sync_result(None)
        mock_build_quota.return_value = MagicMock()
        mock_create_quota.side_effect = RuntimeError("K8s error")

        with pytest.raises(ExternalServiceException, match="K8s"):
            await tenant_service.create_tenant(
                TenantCreateRequest(name="test", display_name="Test"),
            )

        mock_delete_quota.assert_called_once()
        mock_delete_np.assert_called_once()
        mock_delete_ns.assert_called_once()

    @patch("app.services.tenant_service.create_tenant_network_policy")
    @patch("app.services.tenant_service.create_resource_quota")
    @patch("app.services.tenant_service.build_tenant_resource_quota")
    @patch("app.services.tenant_service.create_namespace")
    async def test_create_tenant_ns_failure_rollback(
        self,
        mock_create_ns,
        mock_build_quota,
        mock_create_quota,
        mock_create_np,
        tenant_service,
        mock_db,
    ):
        mock_db.execute.return_value = _sync_result(None)
        mock_create_ns.side_effect = RuntimeError("Namespace error")

        with pytest.raises(ExternalServiceException, match="K8s"):
            await tenant_service.create_tenant(
                TenantCreateRequest(name="test", display_name="Test"),
            )


class TestListTenants:
    async def test_list_tenants_empty(self, tenant_service, mock_db):
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_rows_result = MagicMock()
        mock_rows_result.all.return_value = []

        mock_db.execute.side_effect = [mock_count_result, mock_rows_result]

        items, total = await tenant_service.list_tenants()
        assert items == []
        assert total == 0

    async def test_list_tenants_with_data(self, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        mock_rows_result = MagicMock()
        mock_rows_result.all.return_value = [(tenant, 5)]

        mock_db.execute.side_effect = [mock_count_result, mock_rows_result]

        items, total = await tenant_service.list_tenants(page=1, page_size=20)
        assert total == 1
        assert len(items) == 1
        assert items[0]["name"] == "test-tenant"
        assert items[0]["member_count"] == 5

    async def test_list_tenants_pagination(self, tenant_service, mock_db):
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 50

        mock_rows_result = MagicMock()
        mock_rows_result.all.return_value = []

        mock_db.execute.side_effect = [mock_count_result, mock_rows_result]

        items, total = await tenant_service.list_tenants(page=2, page_size=20)
        assert total == 50
        assert items == []
