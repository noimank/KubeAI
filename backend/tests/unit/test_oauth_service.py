from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import UnauthorizedException
from app.services.oauth_service import OAuthService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def oauth_service(mock_db, mock_redis):
    return OAuthService(mock_db, mock_redis)


class TestGetProviders:
    def test_returns_empty_when_disabled(self, oauth_service):
        with patch("app.services.oauth_service.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = False
            result = oauth_service.get_providers()
            assert result == []

    def test_returns_provider_when_enabled(self, oauth_service):
        with patch("app.services.oauth_service.settings") as mock_settings:
            mock_settings.OIDC_ENABLED = True
            mock_settings.OIDC_DISPLAY_NAME = "SSO 登录"
            result = oauth_service.get_providers()
            assert len(result) == 1
            assert result[0].name == "oidc"
            assert result[0].display_name == "SSO 登录"


class TestHandleCallback:
    async def test_invalid_state_raises_401(self, oauth_service, mock_redis):
        mock_redis.get.return_value = None

        with pytest.raises(UnauthorizedException, match="state"):
            await oauth_service.handle_callback("code", "bad-state", "http://localhost:3000/auth/callback")

    async def test_state_consumed_after_use(self, oauth_service, mock_redis):
        import json

        discovery = {
            "token_endpoint": "https://idp.example.com/token",
            "userinfo_endpoint": "https://idp.example.com/userinfo",
        }
        mock_redis.get.side_effect = ["oidc", json.dumps(discovery)]
        mock_redis.delete = AsyncMock()

        with (
            patch("app.services.oauth_service.AsyncOAuth2Client") as mock_client_cls,
            patch("app.services.oauth_service.settings") as mock_settings,
        ):
            mock_settings.OIDC_CLIENT_ID = "id"
            mock_settings.OIDC_CLIENT_SECRET = "secret"
            mock_settings.OIDC_SCOPES = "openid profile email"

            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_client.fetch_token = AsyncMock(return_value={"access_token": "ext-token"})
            mock_client.get = AsyncMock(
                return_value=MagicMock(
                    status_code=200,
                    json=lambda: {"sub": "ext-123", "email": "user@example.com", "preferred_username": "testuser"},
                )
            )

            mock_db = oauth_service.db
            mock_db.execute = AsyncMock(return_value=_sync_result(None))
            mock_db.flush = AsyncMock()

            await oauth_service.handle_callback("code", "valid-state", "http://localhost:3000/auth/callback")

            mock_redis.delete.assert_called_with("oauth:state:valid-state")


class TestFindOrCreateUser:
    async def test_creates_new_user_on_first_login(self, oauth_service, mock_db):
        mock_db.execute = AsyncMock(return_value=_sync_result(None))
        mock_db.flush = AsyncMock()

        with patch("app.services.oauth_service.hash_password", new=AsyncMock(return_value="hashed")):
            user = await oauth_service._find_or_create_user("ext-123", "testuser", "test@example.com")

        assert user.auth_provider == "oidc"
        assert user.external_id == "ext-123"
        assert user.username == "testuser"
        assert user.email == "test@example.com"

    async def test_links_existing_user_on_subsequent_login(self, oauth_service, mock_db):
        from app.models.user import User

        existing = User(username="testuser", email="test@example.com", hashed_password="hashed")
        existing.auth_provider = "oidc"
        existing.external_id = "ext-123"

        mock_db.execute = AsyncMock(return_value=_sync_result(existing))

        user = await oauth_service._find_or_create_user("ext-123", "testuser", "test@example.com")

        assert user is existing

    async def test_generates_unique_username_on_conflict(self, oauth_service, mock_db):
        from app.models.user import User

        call_count = [0]

        def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return _sync_result(None)
            if call_count[0] == 2:
                return _sync_result(None)
            if call_count[0] == 3:
                conflicting = User(username="testuser", email="other@example.com", hashed_password="hashed")
                return _sync_result(conflicting)
            return _sync_result(None)

        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.flush = AsyncMock()

        with patch("app.services.oauth_service.hash_password", new=AsyncMock(return_value="hashed")):
            user = await oauth_service._find_or_create_user("ext-456", "testuser", "new@example.com")

        assert user.username == "testuser_1"

    async def test_binds_existing_user_when_email_exists(self, oauth_service, mock_db):
        from app.models.user import User

        existing = User(username="localuser", email="taken@example.com", hashed_password="hashed")
        existing.auth_provider = "local"
        existing.external_id = None
        call_count = [0]

        def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return _sync_result(None)
            return _sync_result(existing)

        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.flush = AsyncMock()

        with patch("app.services.oauth_service.hash_password", new=AsyncMock(return_value="hashed")):
            user = await oauth_service._find_or_create_user("ext-789", "newuser", "taken@example.com")

        assert user is existing
        assert user.auth_provider == "oidc"
        assert user.external_id == "ext-789"
        assert user.username == "newuser"
        assert user.email == "taken@example.com"

    async def test_uses_external_id_as_username_fallback(self, oauth_service, mock_db):
        mock_db.execute = AsyncMock(return_value=_sync_result(None))
        mock_db.flush = AsyncMock()

        with patch("app.services.oauth_service.hash_password", new=AsyncMock(return_value="hashed")):
            user = await oauth_service._find_or_create_user("ext-id-abc", "", "")

        assert user.username == "ext-id-abc"
        assert user.email == "ext-id-abc@oauth.local"
