from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import UnauthorizedException
from app.models.enums import UserRole
from app.services.oauth_service import OAuthService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


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


class TestExtractRoleFromUserinfo:
    def test_no_roles_claim_returns_none(self):
        result = OAuthService._extract_role_from_userinfo({"sub": "123"})
        assert result is None

    def test_empty_roles_returns_none(self):
        result = OAuthService._extract_role_from_userinfo({"roles": []})
        assert result is None

    def test_no_kubeai_prefixed_roles_returns_none(self):
        result = OAuthService._extract_role_from_userinfo({"roles": ["app_user", "project_x"]})
        assert result is None

    def test_single_kubeai_role_maps_correctly(self):
        from app.models.enums import UserRole

        result = OAuthService._extract_role_from_userinfo({"roles": ["kubeai_admin"]})
        assert result == UserRole.ADMIN

    def test_multiple_kubeai_roles_picks_highest_priority(self):
        from app.models.enums import UserRole

        result = OAuthService._extract_role_from_userinfo(
            {"roles": ["kubeai_annotator", "kubeai_admin", "kubeai_engineer"]}
        )
        assert result == UserRole.ADMIN

    def test_kubeai_roles_mixed_with_other_roles(self):
        from app.models.enums import UserRole

        result = OAuthService._extract_role_from_userinfo({"roles": ["app_user", "kubeai_mlops", "other_system_role"]})
        assert result == UserRole.MLOPS

    def test_all_kubeai_roles_map_correctly(self):
        from app.models.enums import UserRole

        cases = [
            ("kubeai_admin", UserRole.ADMIN),
            ("kubeai_mlops", UserRole.MLOPS),
            ("kubeai_engineer", UserRole.ENGINEER),
            ("kubeai_annotator", UserRole.ANNOTATOR),
        ]
        for raw, expected in cases:
            result = OAuthService._extract_role_from_userinfo({"roles": [raw]})
            assert result == expected, f"{raw} should map to {expected}"

    def test_unknown_role_name_returns_none(self, caplog):
        result = OAuthService._extract_role_from_userinfo({"roles": ["kubeai_superuser"]})
        assert result is None

    def test_roles_not_a_list_returns_none(self):
        result = OAuthService._extract_role_from_userinfo({"roles": "not-a-list"})
        assert result is None

    def test_highest_priority_picked_among_kubeai_roles(self):
        from app.models.enums import UserRole

        result = OAuthService._extract_role_from_userinfo(
            {"roles": ["kubeai_engineer", "kubeai_annotator", "kubeai_mlops"]}
        )
        assert result == UserRole.MLOPS


class TestSyncOAuthProfileRole:
    async def test_role_synced_when_different(self, oauth_service, mock_db):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hashed")

        await oauth_service._sync_oauth_profile(user, "testuser", "test@example.com", role=UserRole.ADMIN)
        assert user.role == UserRole.ADMIN

    async def test_role_not_changed_when_none_passed(self, oauth_service, mock_db):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hashed")
        original_role = user.role

        await oauth_service._sync_oauth_profile(user, "testuser", "test@example.com", role=None)
        assert user.role == original_role

    async def test_role_not_changed_when_same(self, oauth_service, mock_db):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hashed")
        user.role = UserRole.ENGINEER

        await oauth_service._sync_oauth_profile(user, "testuser", "test@example.com", role=UserRole.ENGINEER)
        assert user.role == UserRole.ENGINEER


class TestSyncOAuthProfileAvatar:
    async def test_avatar_synced_when_provided(self, oauth_service):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hashed")

        await oauth_service._sync_oauth_profile(
            user, "testuser", "test@example.com", avatar="https://idp.example.com/avatar.png"
        )
        assert user.avatar == "https://idp.example.com/avatar.png"

    async def test_avatar_kept_when_not_provided(self, oauth_service):
        from app.models.user import User

        user = User(username="testuser", email="test@example.com", hashed_password="hashed")
        user.avatar = "data:image/png;base64,abc"

        await oauth_service._sync_oauth_profile(user, "testuser", "test@example.com", avatar=None)
        assert user.avatar == "data:image/png;base64,abc"


class TestFindOrCreateUserAvatar:
    async def test_new_user_gets_avatar(self, oauth_service, mock_db):
        mock_db.execute = AsyncMock(return_value=_sync_result(None))
        mock_db.flush = AsyncMock()

        with patch("app.services.oauth_service.hash_password", new=AsyncMock(return_value="hashed")):
            user = await oauth_service._find_or_create_user(
                "ext-123", "testuser", "test@example.com", avatar="https://idp.example.com/avatar.png"
            )

        assert user.avatar == "https://idp.example.com/avatar.png"

    async def test_existing_user_avatar_updated_on_sync(self, oauth_service, mock_db):
        from app.models.user import User

        existing = User(username="testuser", email="test@example.com", hashed_password="hashed")
        existing.auth_provider = "oidc"
        existing.external_id = "ext-123"

        mock_db.execute = AsyncMock(return_value=_sync_result(existing))

        user = await oauth_service._find_or_create_user(
            "ext-123", "testuser", "test@example.com", avatar="https://idp.example.com/new.png"
        )

        assert user is existing
        assert user.avatar == "https://idp.example.com/new.png"


class TestFindOrCreateUserRoleSync:
    async def test_new_user_gets_role_from_oidc(self, oauth_service, mock_db):
        from app.models.enums import UserRole

        mock_db.execute = AsyncMock(return_value=_sync_result(None))
        mock_db.flush = AsyncMock()

        with patch("app.services.oauth_service.hash_password", new=AsyncMock(return_value="hashed")):
            user = await oauth_service._find_or_create_user(
                "ext-123", "testuser", "test@example.com", role=UserRole.MLOPS
            )

        assert user.role == UserRole.MLOPS

    async def test_new_user_defaults_to_engineer_when_no_role(self, oauth_service, mock_db):
        from app.models.enums import UserRole

        mock_db.execute = AsyncMock(return_value=_sync_result(None))
        mock_db.flush = AsyncMock()

        with patch("app.services.oauth_service.hash_password", new=AsyncMock(return_value="hashed")):
            user = await oauth_service._find_or_create_user("ext-123", "testuser", "test@example.com", role=None)

        assert user.role == UserRole.ENGINEER

    async def test_existing_user_role_updated_on_sync(self, oauth_service, mock_db):
        from app.models.enums import UserRole
        from app.models.user import User

        existing = User(username="testuser", email="test@example.com", hashed_password="hashed")
        existing.auth_provider = "oidc"
        existing.external_id = "ext-123"
        existing.role = UserRole.ENGINEER

        mock_db.execute = AsyncMock(return_value=_sync_result(existing))

        user = await oauth_service._find_or_create_user("ext-123", "testuser", "test@example.com", role=UserRole.ADMIN)

        assert user.role == UserRole.ADMIN
