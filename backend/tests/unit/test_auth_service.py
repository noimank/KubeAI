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
def mock_blacklist():
    svc = AsyncMock()
    svc.is_revoked = AsyncMock(return_value=False)
    svc.revoke_token = AsyncMock()
    return svc


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
        assert result.tenant_id is None

    async def test_login_with_tenant_id(self, auth_service, mock_db, mock_redis):
        from app.models.user import User

        tenant_id = uuid.uuid4()
        user = User(
            username="tenantuser", email="tenant@example.com", hashed_password="$2b$12$fakehash", tenant_id=tenant_id
        )
        user.id = uuid.uuid4()

        mock_db.execute.return_value = _sync_result(user)
        mock_redis.get.return_value = None

        with patch("app.services.auth_service.verify_password", return_value=True):
            result = await auth_service.login(LoginRequest(username="tenantuser", password="Passw0rd"))

        assert result.tenant_id == str(tenant_id)

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


class TestRefreshTokens:
    async def test_refresh_success(self, auth_service, mock_blacklist, mock_db):
        from app.core.security import create_refresh_token
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hash")
        token = create_refresh_token({"sub": str(user.id)})
        auth_service.blacklist = mock_blacklist
        mock_db.execute.return_value = _sync_result(user)

        result = await auth_service.refresh_tokens(token)
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.token_type == "bearer"

    async def test_refresh_revokes_old_token(self, auth_service, mock_blacklist, mock_db):
        from app.core.security import create_refresh_token
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hash")
        token = create_refresh_token({"sub": str(user.id)})
        auth_service.blacklist = mock_blacklist
        mock_db.execute.return_value = _sync_result(user)

        await auth_service.refresh_tokens(token)
        mock_blacklist.revoke_token.assert_called_once()

    async def test_refresh_expired_token_raises_401(self, auth_service):
        with (
            patch("app.services.auth_service.decode_token", side_effect=ValueError("expired")),
            pytest.raises(UnauthorizedException, match="无效或过期"),
        ):
            await auth_service.refresh_tokens("expired-token")

    async def test_refresh_revoked_token_raises_401(self, auth_service, mock_blacklist):
        from app.core.security import create_refresh_token

        user_id = str(uuid.uuid4())
        token = create_refresh_token({"sub": user_id})
        mock_blacklist.is_revoked = AsyncMock(return_value=True)
        auth_service.blacklist = mock_blacklist

        with pytest.raises(UnauthorizedException, match="已被吊销"):
            await auth_service.refresh_tokens(token)

    async def test_refresh_user_not_found_raises_401(self, auth_service, mock_blacklist, mock_db):
        from app.core.security import create_refresh_token

        user_id = str(uuid.uuid4())
        token = create_refresh_token({"sub": user_id})
        auth_service.blacklist = mock_blacklist
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(UnauthorizedException, match="用户不存在"):
            await auth_service.refresh_tokens(token)

    async def test_refresh_carries_tenant_id(self, auth_service, mock_blacklist, mock_db):
        from app.core.security import create_refresh_token
        from app.models.user import User

        tenant_id = uuid.uuid4()
        user = User(username="testuser", email="test@example.com", hashed_password="hash", tenant_id=tenant_id)
        token = create_refresh_token({"sub": str(user.id)})
        auth_service.blacklist = mock_blacklist
        mock_db.execute.return_value = _sync_result(user)

        result = await auth_service.refresh_tokens(token)
        assert result.tenant_id == str(tenant_id)

    async def test_refresh_wrong_type_raises_401(self, auth_service, mock_blacklist):
        from app.core.security import create_access_token

        user_id = str(uuid.uuid4())
        token = create_access_token({"sub": user_id})
        auth_service.blacklist = mock_blacklist

        with pytest.raises(UnauthorizedException, match="类型"):
            await auth_service.refresh_tokens(token)


class TestLogout:
    async def test_logout_revokes_access_token(self, auth_service, mock_blacklist):
        auth_service.blacklist = mock_blacklist
        user_id = str(uuid.uuid4())

        await auth_service.logout(user_id, "access-jti")
        mock_blacklist.revoke_token.assert_called_once_with("access-jti", 30 * 60)

    async def test_logout_revokes_both_tokens(self, auth_service, mock_blacklist):
        auth_service.blacklist = mock_blacklist
        user_id = str(uuid.uuid4())

        await auth_service.logout(user_id, "access-jti", "refresh-jti")
        assert mock_blacklist.revoke_token.call_count == 2

    async def test_logout_without_refresh_token(self, auth_service, mock_blacklist):
        auth_service.blacklist = mock_blacklist
        user_id = str(uuid.uuid4())

        await auth_service.logout(user_id, "access-jti", None)
        mock_blacklist.revoke_token.assert_called_once_with("access-jti", 30 * 60)


class TestBuiltinAuthUnaffectedByOIDC:
    async def test_register_still_works(self, auth_service, mock_db):
        mock_db.execute.side_effect = [_sync_result(None), _sync_result(None)]

        result = await auth_service.register(
            RegisterRequest(
                username="oidc_context_user",
                email="oidc@example.com",
                password="Passw0rd",
                confirm_password="Passw0rd",
            )
        )
        assert result.access_token is not None
        assert result.refresh_token is not None

    async def test_login_still_works(self, auth_service, mock_db, mock_redis):
        from app.models.user import User

        user = User(username="oidc_context_user", email="test@example.com", hashed_password="$2b$12$fakehash")
        user.id = uuid.uuid4()

        mock_db.execute.return_value = _sync_result(user)
        mock_redis.get.return_value = None

        with patch("app.services.auth_service.verify_password", return_value=True):
            result = await auth_service.login(LoginRequest(username="oidc_context_user", password="Passw0rd"))
            assert result.access_token is not None
