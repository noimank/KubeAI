import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services.tenant_service import TenantService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_tenant():
    t = Tenant(name="test-tenant", display_name="Test Tenant")
    t.id = uuid.uuid4()
    return t


def _make_user(tenant_id=None, role=UserRole.ENGINEER):
    u = User(
        username="testuser",
        email="test@example.com",
        hashed_password="fake_hash",
    )
    u.role = role
    u.tenant_id = tenant_id
    return u


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return TenantService(mock_db)


class TestListMembers:
    async def test_list_members(self, service, mock_db):
        tenant = _make_tenant()
        user = _make_user(tenant_id=tenant.id)

        tenant_result = _sync_result(tenant)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [user]
        members_result = MagicMock()
        members_result.scalars.return_value = scalars_mock

        mock_db.execute.side_effect = [tenant_result, members_result]

        result = await service.list_members(tenant.id)
        assert len(result) == 1
        assert result[0]["username"] == "testuser"
        assert result[0]["role"] == UserRole.ENGINEER

    async def test_list_members_tenant_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="租户不存在"):
            await service.list_members(uuid.uuid4())


class TestUpdateMemberRole:
    async def test_update_member_role_success(self, service, mock_db):
        tenant = _make_tenant()
        user = _make_user(tenant_id=tenant.id, role=UserRole.ENGINEER)

        mock_db.execute.return_value = _sync_result(user)

        await service.update_member_role(tenant.id, user.id, UserRole.MLOPS, current_user_id=uuid.uuid4())
        assert user.role == UserRole.MLOPS
        mock_db.flush.assert_called_once()

    async def test_update_member_role_cannot_change_self(self, service, mock_db):
        user_id = uuid.uuid4()

        with pytest.raises(BadRequestException, match="不能修改自己的角色"):
            await service.update_member_role(uuid.uuid4(), user_id, UserRole.MLOPS, current_user_id=user_id)

    async def test_update_member_role_cannot_set_admin(self, service, mock_db):
        with pytest.raises(BadRequestException, match="不能将成员角色设为管理员"):
            await service.update_member_role(uuid.uuid4(), uuid.uuid4(), UserRole.ADMIN, current_user_id=uuid.uuid4())

    async def test_update_member_role_user_not_in_tenant(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="该用户不属于此租户"):
            await service.update_member_role(uuid.uuid4(), uuid.uuid4(), UserRole.MLOPS, current_user_id=uuid.uuid4())


class TestRemoveMember:
    async def test_remove_member_success(self, service, mock_db):
        tenant = _make_tenant()
        user = _make_user(tenant_id=tenant.id)

        mock_db.execute.return_value = _sync_result(user)

        await service.remove_member(tenant.id, user.id, current_user_id=uuid.uuid4())
        assert user.tenant_id is None
        mock_db.flush.assert_called_once()

    async def test_remove_member_cannot_remove_self(self, service, mock_db):
        user_id = uuid.uuid4()

        with pytest.raises(BadRequestException, match="不能移除自己"):
            await service.remove_member(uuid.uuid4(), user_id, current_user_id=user_id)

    async def test_remove_member_user_not_in_tenant(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="该用户不属于此租户"):
            await service.remove_member(uuid.uuid4(), uuid.uuid4(), current_user_id=uuid.uuid4())

    async def test_remove_member_preserves_user_account(self, service, mock_db):
        tenant = _make_tenant()
        user = _make_user(tenant_id=tenant.id)

        mock_db.execute.return_value = _sync_result(user)

        await service.remove_member(tenant.id, user.id, current_user_id=uuid.uuid4())
        assert user.tenant_id is None
        mock_db.delete.assert_not_called()
