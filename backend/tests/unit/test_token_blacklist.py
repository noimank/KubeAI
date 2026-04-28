from unittest.mock import AsyncMock

import pytest

from app.core.token_blacklist import TokenBlacklistService


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def blacklist_service(mock_redis):
    return TokenBlacklistService(mock_redis)


class TestRevokeToken:
    async def test_revoke_token_sets_key_with_ttl(self, blacklist_service, mock_redis):
        mock_redis.setex = AsyncMock()

        await blacklist_service.revoke_token("test-jti", 3600)

        mock_redis.setex.assert_called_once_with("token_blacklist:test-jti", 3600, "revoked")

    async def test_revoke_token_with_short_ttl(self, blacklist_service, mock_redis):
        mock_redis.setex = AsyncMock()

        await blacklist_service.revoke_token("short-jti", 60)

        mock_redis.setex.assert_called_once_with("token_blacklist:short-jti", 60, "revoked")


class TestIsRevoked:
    async def test_revoked_token_returns_true(self, blacklist_service, mock_redis):
        mock_redis.exists = AsyncMock(return_value=1)

        result = await blacklist_service.is_revoked("revoked-jti")

        assert result is True
        mock_redis.exists.assert_called_once_with("token_blacklist:revoked-jti")

    async def test_non_revoked_token_returns_false(self, blacklist_service, mock_redis):
        mock_redis.exists = AsyncMock(return_value=0)

        result = await blacklist_service.is_revoked("valid-jti")

        assert result is False
        mock_redis.exists.assert_called_once_with("token_blacklist:valid-jti")


class TestRevokeAllUserTokens:
    async def test_increments_user_token_version(self, blacklist_service, mock_redis):
        mock_redis.incr = AsyncMock(return_value=2)

        await blacklist_service.revoke_all_user_tokens("user-123")

        mock_redis.incr.assert_called_once_with("user_token_version:user-123")

    async def test_first_increment_returns_one(self, blacklist_service, mock_redis):
        mock_redis.incr = AsyncMock(return_value=1)

        await blacklist_service.revoke_all_user_tokens("user-456")

        mock_redis.incr.assert_called_once_with("user_token_version:user-456")
