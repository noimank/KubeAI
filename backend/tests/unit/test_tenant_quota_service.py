import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    BadRequestException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.models.enums import TenantStatus
from app.models.tenant import Tenant
from app.schemas.tenant import TenantQuotaUpdateRequest
from app.services.tenant_service import TenantService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_tenant(name="test-tenant"):
    t = Tenant(name=name, display_name=name, description=None)
    t.id = uuid.uuid4()
    t.status = TenantStatus.ACTIVE
    t.gpu_limit = 0
    t.cpu_limit = "4"
    t.memory_limit = "8Gi"
    t.storage_limit = "10Gi"
    t.k8s_namespace_name = f"kubeai-{t.id}"
    return t


def _quota_req(gpu=8, cpu="32", memory="64Gi", storage="100Gi", force=False):
    return TenantQuotaUpdateRequest(
        gpu_limit=gpu, cpu_limit=cpu, memory_limit=memory, storage_limit=storage, force=force
    )


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def tenant_service(mock_db):
    return TenantService(mock_db)


class TestUpdateQuota:
    @patch("app.services.tenant_service.update_resource_quota")
    @patch("app.services.tenant_service.get_quota_used")
    @patch("app.services.tenant_service.get_cluster_capacity")
    async def test_update_quota_success(self, mock_capacity, mock_used, mock_k8s_update, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_db.refresh = AsyncMock(return_value=None)
        mock_capacity.return_value = {"gpu": "16", "cpu": "128", "memory": "512GiKi"}
        mock_used.return_value = {
            "requests.nvidia.com/gpu": "0",
            "requests.cpu": "0",
            "requests.memory": "0",
            "requests.storage": "0",
        }

        result = await tenant_service.update_quota(tenant.id, _quota_req(gpu=8))

        assert result.gpu_limit == 8
        assert result.cpu_limit == "32"
        mock_k8s_update.assert_called_once()

    @patch("app.services.tenant_service.update_resource_quota")
    @patch("app.services.tenant_service.get_quota_used")
    @patch("app.services.tenant_service.get_cluster_capacity")
    async def test_update_quota_exceeds_cluster(
        self, mock_capacity, mock_used, mock_k8s_update, tenant_service, mock_db
    ):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_capacity.return_value = {"gpu": "4", "cpu": "64", "memory": "256GiKi"}

        with pytest.raises(QuotaExceededException, match="超过集群可用资源"):
            await tenant_service.update_quota(tenant.id, _quota_req(gpu=8))

    @patch("app.services.tenant_service.update_resource_quota")
    @patch("app.services.tenant_service.get_quota_used")
    @patch("app.services.tenant_service.get_cluster_capacity")
    async def test_update_quota_usage_exceeds_new(
        self, mock_capacity, mock_used, mock_k8s_update, tenant_service, mock_db
    ):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_capacity.return_value = {"gpu": "16", "cpu": "128", "memory": "512GiKi"}
        mock_used.return_value = {
            "requests.nvidia.com/gpu": "10",
            "requests.cpu": "2",
            "requests.memory": "4Gi",
            "requests.storage": "10Gi",
        }

        with pytest.raises(QuotaExceededException, match="使用量"):
            await tenant_service.update_quota(tenant.id, _quota_req(gpu=8))

    @patch("app.services.tenant_service.update_resource_quota")
    @patch("app.services.tenant_service.get_quota_used")
    @patch("app.services.tenant_service.get_cluster_capacity")
    async def test_update_quota_force_bypasses_usage(
        self, mock_capacity, mock_used, mock_k8s_update, tenant_service, mock_db
    ):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_db.refresh = AsyncMock(return_value=None)
        mock_capacity.return_value = {"gpu": "16", "cpu": "128", "memory": "512GiKi"}
        mock_used.return_value = {
            "requests.nvidia.com/gpu": "10",
            "requests.cpu": "2",
            "requests.memory": "4Gi",
            "requests.storage": "10Gi",
        }

        result = await tenant_service.update_quota(tenant.id, _quota_req(gpu=8, force=True))

        assert result.gpu_limit == 8
        mock_k8s_update.assert_called_once()

    async def test_update_quota_no_namespace(self, tenant_service, mock_db):
        tenant = _make_tenant()
        tenant.k8s_namespace_name = None
        mock_db.execute.return_value = _sync_result(tenant)

        with pytest.raises(BadRequestException, match="命名空间"):
            await tenant_service.update_quota(tenant.id, _quota_req())

    async def test_update_quota_tenant_not_found(self, tenant_service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="租户不存在"):
            await tenant_service.update_quota(uuid.uuid4(), _quota_req())

    @patch("app.services.tenant_service.update_resource_quota")
    @patch("app.services.tenant_service.get_quota_used")
    @patch("app.services.tenant_service.get_cluster_capacity")
    async def test_update_quota_k8s_sync_failure(
        self, mock_capacity, mock_used, mock_k8s_update, tenant_service, mock_db
    ):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_db.refresh = AsyncMock(return_value=None)
        mock_capacity.return_value = {"gpu": "16", "cpu": "128", "memory": "512GiKi"}
        mock_used.return_value = {
            "requests.nvidia.com/gpu": "0",
            "requests.cpu": "0",
            "requests.memory": "0",
            "requests.storage": "0",
        }
        mock_k8s_update.side_effect = RuntimeError("K8s down")

        with pytest.raises(ExternalServiceException, match="K8s"):
            await tenant_service.update_quota(tenant.id, _quota_req())

    @patch("app.services.tenant_service.get_quota_used")
    @patch("app.services.tenant_service.get_cluster_capacity")
    async def test_update_quota_cluster_capacity_failure(self, mock_capacity, mock_used, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_capacity.side_effect = RuntimeError("K8s unreachable")

        with pytest.raises(ExternalServiceException, match="集群资源"):
            await tenant_service.update_quota(tenant.id, _quota_req())


class TestGetQuotaUsage:
    @patch("app.services.tenant_service.get_quota_used")
    async def test_get_quota_usage_success(self, mock_used, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_used.return_value = {
            "requests.nvidia.com/gpu": "3",
            "requests.cpu": "8",
            "requests.memory": "16Gi",
            "requests.storage": "50Gi",
        }

        result = await tenant_service.get_quota_usage(tenant.id)
        assert result["gpu_used"] == 3
        assert result["cpu_used"] == "8"
        assert result["memory_used"] == "16Gi"
        assert result["storage_used"] == "50Gi"

    async def test_get_quota_usage_no_namespace(self, tenant_service, mock_db):
        tenant = _make_tenant()
        tenant.k8s_namespace_name = None
        mock_db.execute.return_value = _sync_result(tenant)

        result = await tenant_service.get_quota_usage(tenant.id)
        assert result["gpu_used"] == 0
        assert result["cpu_used"] == "0"

    @patch("app.services.tenant_service.get_quota_used")
    async def test_get_quota_usage_k8s_failure(self, mock_used, tenant_service, mock_db):
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_used.side_effect = RuntimeError("K8s down")

        with pytest.raises(ExternalServiceException, match="配额使用量"):
            await tenant_service.get_quota_usage(tenant.id)

    async def test_get_quota_usage_not_found(self, tenant_service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="租户不存在"):
            await tenant_service.get_quota_usage(uuid.uuid4())
