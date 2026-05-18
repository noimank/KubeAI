from unittest.mock import patch

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHash:
    async def test_hash_password_returns_hash(self):
        hashed = await hash_password("mypassword")
        assert isinstance(hashed, str)
        assert hashed != "mypassword"

    async def test_hash_password_different_each_time(self):
        h1 = await hash_password("samepassword")
        h2 = await hash_password("samepassword")
        assert h1 != h2

    async def test_verify_password_correct(self):
        hashed = await hash_password("mypassword")
        assert await verify_password("mypassword", hashed) is True

    async def test_verify_password_incorrect(self):
        hashed = await hash_password("mypassword")
        assert await verify_password("wrongpassword", hashed) is False


class TestAccessToken:
    def test_create_access_token_returns_string(self):
        token = create_access_token({"sub": "user-123"})
        assert isinstance(token, str)

    def test_decode_valid_access_token(self):
        token = create_access_token({"sub": "user-123"})
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_access_token_has_exp(self):
        token = create_access_token({"sub": "user-123"})
        payload = decode_token(token)
        assert "exp" in payload


class TestRefreshToken:
    def test_create_refresh_token_returns_string(self):
        token = create_refresh_token({"sub": "user-123"})
        assert isinstance(token, str)

    def test_decode_valid_refresh_token(self):
        token = create_refresh_token({"sub": "user-123"})
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"


class TestTokenExpiration:
    def test_expired_token_raises(self):
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = -1
            token = create_access_token({"sub": "user-123"})

        with pytest.raises(ValueError, match="无效或过期的 Token"):
            decode_token(token)
