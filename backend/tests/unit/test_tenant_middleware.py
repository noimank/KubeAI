import uuid
from unittest.mock import MagicMock

from app.api.deps import get_current_tenant_id
from app.models.enums import UserRole
from app.models.user import User


def _make_user(tenant_id: uuid.UUID | None = None, role: UserRole = UserRole.ENGINEER):
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hash",
        tenant_id=tenant_id,
        role=role,
    )
    return user


class TestGetCurrentTenantId:
    async def test_returns_tenant_id_when_user_has_tenant(self):
        tenant_id = uuid.uuid4()
        _make_user(tenant_id=tenant_id)

        request = MagicMock()
        request.state.tenant_id = str(tenant_id)

        result = await get_current_tenant_id(request)
        assert result == str(tenant_id)

    async def test_returns_none_when_user_has_no_tenant(self):
        request = MagicMock()
        request.state.tenant_id = None

        result = await get_current_tenant_id(request)
        assert result is None

    async def test_returns_none_when_state_has_no_tenant_id(self):
        request = MagicMock()
        del request.state.tenant_id

        result = await get_current_tenant_id(request)
        assert result is None
