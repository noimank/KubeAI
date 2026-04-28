import uuid

import pytest

from app.api.deps import require_tenant_access
from app.core.exceptions import ForbiddenException
from app.models.enums import UserRole
from app.models.user import User


def _make_user(tenant_id: uuid.UUID | None = None, role: UserRole = UserRole.ENGINEER):
    return User(
        username="testuser",
        email="test@example.com",
        hashed_password="hash",
        tenant_id=tenant_id,
        role=role,
    )


class TestRequireTenantAccess:
    @pytest.mark.asyncio
    async def test_same_tenant_access_allowed(self):
        tenant_id = uuid.uuid4()
        user = _make_user(tenant_id=tenant_id)
        check = require_tenant_access(tenant_id)
        result = await check(user)
        assert result == user

    @pytest.mark.asyncio
    async def test_cross_tenant_access_denied(self):
        user = _make_user(tenant_id=uuid.uuid4())
        other_tenant = uuid.uuid4()
        check = require_tenant_access(other_tenant)
        with pytest.raises(ForbiddenException, match="无权访问"):
            await check(user)

    @pytest.mark.asyncio
    async def test_admin_exemption(self):
        admin = _make_user(tenant_id=uuid.uuid4(), role=UserRole.ADMIN)
        other_tenant = uuid.uuid4()
        check = require_tenant_access(other_tenant)
        result = await check(admin)
        assert result == admin

    @pytest.mark.asyncio
    async def test_user_without_tenant_denied(self):
        user = _make_user(tenant_id=None)
        resource_tenant = uuid.uuid4()
        check = require_tenant_access(resource_tenant)
        with pytest.raises(ForbiddenException, match="无权访问"):
            await check(user)
