import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.models.user import User


def _make_credentials(token: str) -> MagicMock:
    creds = MagicMock()
    creds.credentials = token
    return creds


def _make_user(user_id: str | None = None, is_active: bool = True) -> User:
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hash",
    )
    if user_id:
        user.id = uuid.UUID(user_id)
    user.is_active = is_active
    return user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def mock_blacklist():
    svc = AsyncMock()
    svc.is_revoked = AsyncMock(return_value=False)
    return svc


class TestGetCurrentUser:
    @patch("app.api.deps.TokenBlacklistService")
    @patch("app.api.deps.decode_token")
    async def test_valid_token_returns_user(self, mock_decode, mock_bl_cls, mock_db, mock_redis, mock_blacklist):
        user_id = str(uuid.uuid4())
        mock_decode.return_value = {"sub": user_id, "type": "access", "jti": "jti-1"}
        mock_bl_cls.return_value = mock_blacklist
        mock_db.execute = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=_make_user(user_id)))

        from app.api.deps import get_current_user

        user = await get_current_user(_make_credentials("valid-token"), mock_db, mock_redis)
        assert user is not None
        assert str(user.id) == user_id

    @patch("app.api.deps.decode_token", side_effect=ValueError("bad token"))
    async def test_invalid_token_raises_401(self, mock_decode, mock_db, mock_redis):
        from app.api.deps import get_current_user

        with pytest.raises(UnauthorizedException):
            await get_current_user(_make_credentials("bad-token"), mock_db, mock_redis)

    @patch("app.api.deps.TokenBlacklistService")
    @patch("app.api.deps.decode_token")
    async def test_expired_token_raises_401(self, mock_decode, mock_bl_cls, mock_db, mock_redis, mock_blacklist):
        mock_decode.return_value = {"sub": str(uuid.uuid4()), "type": "access", "jti": "jti-2"}
        mock_bl_cls.return_value = mock_blacklist
        mock_db.execute = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        from app.api.deps import get_current_user

        with pytest.raises(UnauthorizedException, match="用户不存在"):
            await get_current_user(_make_credentials("expired-token"), mock_db, mock_redis)

    @patch("app.api.deps.TokenBlacklistService")
    @patch("app.api.deps.decode_token")
    async def test_blacklisted_token_raises_401(self, mock_decode, mock_bl_cls, mock_db, mock_redis, mock_blacklist):
        mock_decode.return_value = {"sub": str(uuid.uuid4()), "type": "access", "jti": "jti-3"}
        mock_blacklist.is_revoked = AsyncMock(return_value=True)
        mock_bl_cls.return_value = mock_blacklist

        from app.api.deps import get_current_user

        with pytest.raises(UnauthorizedException, match="已被吊销"):
            await get_current_user(_make_credentials("revoked-token"), mock_db, mock_redis)

    @patch("app.api.deps.TokenBlacklistService")
    @patch("app.api.deps.decode_token")
    async def test_inactive_user_raises_403(self, mock_decode, mock_bl_cls, mock_db, mock_redis, mock_blacklist):
        user_id = str(uuid.uuid4())
        mock_decode.return_value = {"sub": user_id, "type": "access", "jti": "jti-4"}
        mock_bl_cls.return_value = mock_blacklist
        mock_db.execute = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=_make_user(user_id, is_active=False))
        )

        from app.api.deps import get_current_user

        with pytest.raises(ForbiddenException, match="已被禁用"):
            await get_current_user(_make_credentials("valid-token"), mock_db, mock_redis)

    @patch("app.api.deps.decode_token")
    async def test_no_token_raises_401(self, mock_decode, mock_db, mock_redis):
        mock_decode.side_effect = ValueError("no token")

        from app.api.deps import get_current_user

        with pytest.raises(UnauthorizedException):
            await get_current_user(_make_credentials(""), mock_db, mock_redis)

    @patch("app.api.deps.TokenBlacklistService")
    @patch("app.api.deps.decode_token")
    async def test_wrong_token_type_raises_401(self, mock_decode, mock_bl_cls, mock_db, mock_redis, mock_blacklist):
        mock_decode.return_value = {"sub": str(uuid.uuid4()), "type": "refresh", "jti": "jti-5"}
        mock_bl_cls.return_value = mock_blacklist

        from app.api.deps import get_current_user

        with pytest.raises(UnauthorizedException, match="类型"):
            await get_current_user(_make_credentials("refresh-token"), mock_db, mock_redis)

    @patch("app.api.deps.TokenBlacklistService")
    @patch("app.api.deps.decode_token")
    async def test_missing_jti_raises_401(self, mock_decode, mock_bl_cls, mock_db, mock_redis, mock_blacklist):
        mock_decode.return_value = {"sub": str(uuid.uuid4()), "type": "access"}
        mock_bl_cls.return_value = mock_blacklist

        from app.api.deps import get_current_user

        with pytest.raises(UnauthorizedException, match="无效"):
            await get_current_user(_make_credentials("no-jti-token"), mock_db, mock_redis)
