import uuid

from app.models.enums import TenantStatus
from app.models.tenant import Tenant
from app.models.user import User


class TestTenantModel:
    def test_tenant_table_name(self):
        assert Tenant.__tablename__ == "tenants"

    def test_tenant_model_fields(self):
        tenant = Tenant(
            name="test-tenant",
            display_name="Test Tenant",
            description="A test tenant",
            k8s_namespace_name="kubeai-test",
        )
        assert tenant.name == "test-tenant"
        assert tenant.display_name == "Test Tenant"
        assert tenant.description == "A test tenant"
        assert tenant.k8s_namespace_name == "kubeai-test"

    def test_tenant_default_values(self):
        tenant = Tenant(
            name="test-tenant",
            display_name="Test Tenant",
        )
        assert tenant.status == TenantStatus.ACTIVE
        assert isinstance(tenant.id, uuid.UUID)
        assert tenant.description is None
        assert tenant.k8s_namespace_name is None

    def test_tenant_inherits_timestamp_mixin(self):
        assert hasattr(Tenant, "created_at")
        assert hasattr(Tenant, "updated_at")

    def test_tenant_status_enum_values(self):
        assert set(e.value for e in TenantStatus) == {"active", "disabled"}

    def test_tenant_status_can_be_disabled(self):
        tenant = Tenant(
            name="disabled-tenant",
            display_name="Disabled Tenant",
            status=TenantStatus.DISABLED,
        )
        assert tenant.status == TenantStatus.DISABLED


class TestUserTenantField:
    def test_user_has_tenant_id_field(self):
        assert hasattr(User, "tenant_id")

    def test_user_tenant_id_default_is_none(self):
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed",
        )
        assert user.tenant_id is None

    def test_user_tenant_id_can_be_set(self):
        tenant_id = uuid.uuid4()
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed",
            tenant_id=tenant_id,
        )
        assert user.tenant_id == tenant_id

    def test_user_has_tenant_relationship(self):
        assert hasattr(User, "tenant")
