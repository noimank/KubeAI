import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, UnauthorizedException
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth_service import AuthService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def auth_service(mock_db, mock_redis):
    return AuthService(mock_db, mock_redis)


class TestRegister:
    async def test_register_success(self, auth_service, mock_db):
        mock_db.execute.side_effect = [_sync_result(None), _sync_result(None)]

        result = await auth_service.register(
            RegisterRequest(
                username="newuser",
                email="new@example.com",
                password="Passw0rd",
                confirm_password="Passw0rd",
            )
        )
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.token_type == "bearer"

    async def test_register_duplicate_username(self, auth_service, mock_db):
        from app.models.user import User

        existing_user = User(username="existing", email="other@example.com", hashed_password="hash")
        mock_db.execute.return_value = _sync_result(existing_user)

        with pytest.raises(ConflictException, match="用户名"):
            await auth_service.register(
                RegisterRequest(
                    username="existing",
                    email="new@example.com",
                    password="Passw0rd",
                    confirm_password="Passw0rd",
                )
            )

    async def test_register_duplicate_email(self, auth_service, mock_db):
        mock_db.execute.side_effect = [_sync_result(None), _sync_result(MagicMock())]

        with pytest.raises(ConflictException, match="邮箱"):
            await auth_service.register(
                RegisterRequest(
                    username="newuser",
                    email="existing@example.com",
                    password="Passw0rd",
                    confirm_password="Passw0rd",
                )
            )


class TestLogin:
    async def test_login_success(self, auth_service, mock_db, mock_redis):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="$2b$12$fakehash")
        user.id = uuid.uuid4()

        mock_db.execute.return_value = _sync_result(user)
        mock_redis.get.return_value = None

        with patch("app.services.auth_service.verify_password", return_value=True):
            result = await auth_service.login(LoginRequest(username="testuser", password="Passw0rd"))

        assert result.access_token is not None
        assert result.refresh_token is not None

    async def test_login_user_not_found(self, auth_service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(UnauthorizedException, match="用户名或密码错误"):
            await auth_service.login(LoginRequest(username="nouser", password="Passw0rd"))

    async def test_login_wrong_password(self, auth_service, mock_db, mock_redis):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hash")
        user.id = uuid.uuid4()

        mock_db.execute.return_value = _sync_result(user)
        mock_redis.get.return_value = None
        mock_redis.incr.return_value = 1

        with (
            patch("app.services.auth_service.verify_password", return_value=False),
            pytest.raises(UnauthorizedException, match="用户名或密码错误"),
        ):
            await auth_service.login(LoginRequest(username="testuser", password="wrong"))

    async def test_login_locked_account(self, auth_service, mock_db, mock_redis):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hash")
        user.id = uuid.uuid4()

        mock_db.execute.return_value = _sync_result(user)

        lock_ttl = 600
        mock_redis.get.return_value = str(lock_ttl)

        with pytest.raises(UnauthorizedException, match="锁定"):
            await auth_service.login(LoginRequest(username="testuser", password="Passw0rd"))

    async def test_login_lock_expired_auto_unlock(self, auth_service, mock_db, mock_redis):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hash")
        user.id = uuid.uuid4()

        mock_db.execute.return_value = _sync_result(user)
        mock_redis.get.side_effect = [None, None]
        mock_redis.incr.return_value = 5

        with (
            patch("app.services.auth_service.verify_password", return_value=False),
            pytest.raises(UnauthorizedException, match="用户名或密码错误"),
        ):
            await auth_service.login(LoginRequest(username="testuser", password="wrong"))

        mock_redis.setex.assert_called()
