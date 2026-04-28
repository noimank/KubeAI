import uuid
from unittest.mock import MagicMock

from app.models.base import TenantMixin
from app.utils.tenant_filter import apply_tenant_filter


class FakeTenantModel(TenantMixin):
    __tablename__ = "fake_tenant"
    tenant_id = MagicMock()


class FakeNonTenantModel:
    pass


class TestApplyTenantFilter:
    def test_adds_filter_for_tenant_mixin_model(self):
        tenant_id = uuid.uuid4()
        query = MagicMock()
        query.where.return_value = "filtered_query"

        result = apply_tenant_filter(query, FakeTenantModel, tenant_id)
        query.where.assert_called_once()
        assert result == "filtered_query"

    def test_no_filter_for_non_tenant_model(self):
        tenant_id = uuid.uuid4()
        query = MagicMock()

        result = apply_tenant_filter(query, FakeNonTenantModel, tenant_id)
        query.where.assert_not_called()
        assert result is query
