import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import UserRole
from app.models.user import User
from app.services.user_service import UserService


def _make_user(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "username": "testuser",
        "email": "test@example.com",
        "hashed_password": "hash",
        "role": UserRole.ENGINEER,
        "is_active": True,
        "auth_provider": "local",
        "tenant_id": None,
        "failed_login_attempts": 0,
        "locked_until": None,
    }
    defaults.update(overrides)
    user = MagicMock(spec=User)
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


def _db_result(value=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalars.return_value.all.return_value = []
    result.one_or_none.return_value = None
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def user_service(mock_db):
    return UserService(mock_db)


class TestListUsers:
    async def test_list_users_basic(self, user_service, mock_db):
        user = _make_user()
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [user]
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        mock_db.execute.side_effect = [count_result, items_result]
        items, total = await user_service.list_users(page=1, page_size=20)

        assert total == 1
        assert len(items) == 1
        assert items[0]["username"] == "testuser"

    async def test_list_users_with_filters(self, user_service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, items_result]
        _items, total = await user_service.list_users(
            username="test", email="test@", role=UserRole.ADMIN, is_active=True
        )
        assert total == 0

    async def test_list_users_with_tenant_name(self, user_service, mock_db):
        tenant_id = uuid.uuid4()
        user = _make_user(tenant_id=tenant_id)
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [user]
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        tenant_result = MagicMock()
        tenant_result.all.return_value = [(tenant_id, "TestTenant")]

        mock_db.execute.side_effect = [count_result, items_result, tenant_result]
        items, _total = await user_service.list_users()

        assert items[0]["tenant_name"] == "TestTenant"


class TestGetUser:
    async def test_get_user_found(self, user_service, mock_db):
        user = _make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        detail = await user_service.get_user(user.id)
        assert detail["username"] == "testuser"
        assert detail["email"] == "test@example.com"

    async def test_get_user_not_found(self, user_service, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(NotFoundException, match="用户不存在"):
            await user_service.get_user(uuid.uuid4())

    async def test_get_user_with_tenant(self, user_service, mock_db):
        tenant_id = uuid.uuid4()
        user = _make_user(tenant_id=tenant_id)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        tenant_result = MagicMock()
        tenant_result.one_or_none.return_value = ("TestTenant",)

        mock_db.execute.side_effect = [user_result, tenant_result]
        detail = await user_service.get_user(user.id)
        assert detail["tenant_name"] == "TestTenant"


class TestUpdateUser:
    async def test_update_role(self, user_service, mock_db):
        user = _make_user(role=UserRole.ENGINEER)
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        with patch.object(user_service, "get_user", return_value={"username": "testuser"}):
            await user_service.update_user(user.id, {"role": UserRole.MLOPS})

        assert user.role == UserRole.MLOPS
        mock_db.flush.assert_called_once()

    async def test_update_tenant(self, user_service, mock_db):
        user = _make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        new_tenant_id = uuid.uuid4()
        with patch.object(user_service, "get_user", return_value={"username": "testuser"}):
            await user_service.update_user(user.id, {"tenant_id": new_tenant_id})

        assert user.tenant_id == new_tenant_id

    async def test_update_user_not_found(self, user_service, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(NotFoundException, match="用户不存在"):
            await user_service.update_user(uuid.uuid4(), {"role": UserRole.ADMIN})

    async def test_update_with_audit(self, user_service, mock_db):
        user = _make_user(role=UserRole.ENGINEER)
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        audit_ctx = {"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"}
        with (
            patch.object(user_service, "get_user", return_value={"username": "testuser"}),
            patch("app.services.user_service.AuditService") as mock_audit_cls,
        ):
            mock_audit_svc = AsyncMock()
            mock_audit_cls.return_value = mock_audit_svc
            await user_service.update_user(user.id, {"role": UserRole.MLOPS}, audit_context=audit_ctx)
            mock_audit_svc.log_action.assert_called_once()


class TestToggleUserStatus:
    async def test_disable_user(self, user_service, mock_db):
        user = _make_user(is_active=True)
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        with patch.object(user_service, "get_user", return_value={"is_active": False}):
            await user_service.toggle_user_status(user.id, False)

        assert user.is_active is False
        mock_db.flush.assert_called_once()

    async def test_enable_user_resets_lock(self, user_service, mock_db):
        user = _make_user(is_active=False, failed_login_attempts=5, locked_until=MagicMock())
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        with patch.object(user_service, "get_user", return_value={"is_active": True}):
            await user_service.toggle_user_status(user.id, True)

        assert user.is_active is True
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

    async def test_toggle_same_status_raises(self, user_service, mock_db):
        user = _make_user(is_active=True)
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        with pytest.raises(ConflictException, match="已处于"):
            await user_service.toggle_user_status(user.id, True)

    async def test_toggle_user_not_found(self, user_service, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(NotFoundException, match="用户不存在"):
            await user_service.toggle_user_status(uuid.uuid4(), False)


class TestDeleteUser:
    async def test_delete_user_soft_delete(self, user_service, mock_db):
        user = _make_user(is_active=True)
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        await user_service.delete_user(user.id)

        assert user.is_active is False
        assert user.deleted_at is not None
        mock_db.flush.assert_called_once()

    async def test_delete_user_not_found(self, user_service, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(NotFoundException, match="用户不存在"):
            await user_service.delete_user(uuid.uuid4())

    async def test_delete_with_audit(self, user_service, mock_db):
        user = _make_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        audit_ctx = {"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"}
        with patch("app.services.user_service.AuditService") as mock_audit_cls:
            mock_audit_svc = AsyncMock()
            mock_audit_cls.return_value = mock_audit_svc
            await user_service.delete_user(user.id, audit_context=audit_ctx)
            mock_audit_svc.log_action.assert_called_once()
