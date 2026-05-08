import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, ExternalServiceException, NotFoundException
from app.models.enums import TenantStatus
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreateRequest, TenantUpdateRequest
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
        assert result.k8s_namespace_name == "kubeai-test"
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


class TestGetTenant:
    async def test_get_tenant_found(self, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)

        result = await tenant_service.get_tenant(tenant.id)
        assert result.name == "test-tenant"

    async def test_get_tenant_not_found(self, tenant_service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="租户不存在"):
            await tenant_service.get_tenant(uuid.uuid4())

    async def test_get_tenant_detail(self, tenant_service, mock_db):
        tenant = _make_tenant()
        tenant_result = _sync_result(tenant)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 3

        mock_db.execute.side_effect = [tenant_result, count_result]

        detail = await tenant_service.get_tenant_detail(tenant.id)
        assert detail["name"] == "test-tenant"
        assert detail["member_count"] == 3

    async def test_get_tenant_detail_not_found(self, tenant_service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="租户不存在"):
            await tenant_service.get_tenant_detail(uuid.uuid4())


class TestUpdateTenant:
    async def test_update_display_name(self, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_db.refresh = AsyncMock(return_value=None)

        result = await tenant_service.update_tenant(
            tenant.id,
            TenantUpdateRequest(display_name="New Name"),
        )
        assert result.display_name == "New Name"

    async def test_update_description(self, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_db.refresh = AsyncMock(return_value=None)

        result = await tenant_service.update_tenant(
            tenant.id,
            TenantUpdateRequest(description="New description"),
        )
        assert result.description == "New description"

    async def test_update_tenant_not_found(self, tenant_service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="租户不存在"):
            await tenant_service.update_tenant(
                uuid.uuid4(),
                TenantUpdateRequest(display_name="X"),
            )


class TestToggleTenantStatus:
    async def test_disable_tenant(self, tenant_service, mock_db):
        tenant = _make_tenant()
        assert tenant.status == TenantStatus.ACTIVE
        mock_db.execute.return_value = _sync_result(tenant)
        mock_db.refresh = AsyncMock(return_value=None)

        result = await tenant_service.toggle_tenant_status(tenant.id, TenantStatus.DISABLED)
        assert result.status == TenantStatus.DISABLED

    async def test_enable_tenant(self, tenant_service, mock_db):
        tenant = _make_tenant()
        tenant.status = TenantStatus.DISABLED
        mock_db.execute.return_value = _sync_result(tenant)
        mock_db.refresh = AsyncMock(return_value=None)

        result = await tenant_service.toggle_tenant_status(tenant.id, TenantStatus.ACTIVE)
        assert result.status == TenantStatus.ACTIVE

    async def test_disable_already_disabled(self, tenant_service, mock_db):
        tenant = _make_tenant()
        tenant.status = TenantStatus.DISABLED
        mock_db.execute.return_value = _sync_result(tenant)

        with pytest.raises(ConflictException, match="租户已被禁用"):
            await tenant_service.toggle_tenant_status(tenant.id, TenantStatus.DISABLED)

    async def test_enable_already_active(self, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)

        with pytest.raises(ConflictException, match="租户已处于启用状态"):
            await tenant_service.toggle_tenant_status(tenant.id, TenantStatus.ACTIVE)

    async def test_toggle_not_found(self, tenant_service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="租户不存在"):
            await tenant_service.toggle_tenant_status(uuid.uuid4(), TenantStatus.DISABLED)


class TestDeleteTenant:
    @patch("app.services.tenant_service.delete_namespace")
    @patch("app.services.tenant_service.delete_network_policy")
    @patch("app.services.tenant_service.delete_resource_quota")
    async def test_delete_tenant_no_members(self, mock_del_quota, mock_del_np, mock_del_ns, tenant_service, mock_db):
        tenant = _make_tenant()
        tenant.k8s_namespace_name = "kubeai-test"
        tenant_result = _sync_result(tenant)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [tenant_result, count_result]
        mock_db.delete = AsyncMock()

        await tenant_service.delete_tenant(tenant.id)

        mock_del_quota.assert_called_once_with("kubeai-test")
        mock_del_np.assert_called_once_with("kubeai-test")
        mock_del_ns.assert_called_once_with("kubeai-test")
        mock_db.delete.assert_called_once_with(tenant)

    async def test_delete_tenant_with_members(self, tenant_service, mock_db):
        tenant = _make_tenant()
        tenant_result = _sync_result(tenant)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 5

        mock_db.execute.side_effect = [tenant_result, count_result]

        with pytest.raises(ConflictException, match="请先移除租户下的所有成员"):
            await tenant_service.delete_tenant(tenant.id)

    @patch("app.services.tenant_service.delete_namespace")
    @patch("app.services.tenant_service.delete_network_policy")
    @patch("app.services.tenant_service.delete_resource_quota")
    async def test_delete_tenant_k8s_failure_continues(
        self, mock_del_quota, mock_del_np, mock_del_ns, tenant_service, mock_db
    ):
        tenant = _make_tenant()
        tenant.k8s_namespace_name = "kubeai-test"
        tenant_result = _sync_result(tenant)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [tenant_result, count_result]
        mock_db.delete = AsyncMock()

        mock_del_quota.side_effect = RuntimeError("K8s down")

        await tenant_service.delete_tenant(tenant.id)

        mock_del_np.assert_called_once()
        mock_del_ns.assert_called_once()
        mock_db.delete.assert_called_once_with(tenant)

    async def test_delete_tenant_not_found(self, tenant_service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="租户不存在"):
            await tenant_service.delete_tenant(uuid.uuid4())
