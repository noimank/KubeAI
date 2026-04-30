import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse


class TestRegisterRequest:
    def test_valid_input(self):
        req = RegisterRequest(
            username="testuser",
            email="test@example.com",
            password="Passw0rd",
            confirm_password="Passw0rd",
        )
        assert req.username == "testuser"
        assert req.email == "test@example.com"

    def test_password_mismatch(self):
        with pytest.raises(ValidationError, match="confirm_password"):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="Passw0rd",
                confirm_password="Different1",
            )

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="Ab1",
                confirm_password="Ab1",
            )

    def test_password_no_uppercase(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="password1",
                confirm_password="password1",
            )

    def test_password_no_lowercase(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="PASSWORD1",
                confirm_password="PASSWORD1",
            )

    def test_password_no_digit(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="testuser",
                email="test@example.com",
                password="Password",
                confirm_password="Password",
            )

    def test_password_exactly_8_chars(self):
        req = RegisterRequest(
            username="testuser",
            email="test@example.com",
            password="Passw0rd",
            confirm_password="Passw0rd",
        )
        assert req.password == "Passw0rd"

    def test_empty_username(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="",
                email="test@example.com",
                password="Passw0rd",
                confirm_password="Passw0rd",
            )

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="testuser",
                email="not-an-email",
                password="Passw0rd",
                confirm_password="Passw0rd",
            )


class TestLoginRequest:
    def test_valid_input(self):
        req = LoginRequest(username="testuser", password="Passw0rd")
        assert req.username == "testuser"
        assert req.password == "Passw0rd"

    def test_empty_username(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="Passw0rd")

    def test_empty_password(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="testuser", password="")


class TestTokenResponse:
    def test_valid_response(self):
        resp = TokenResponse(
            access_token="access.jwt.token",
            refresh_token="refresh.jwt.token",
            token_type="bearer",
        )
        assert resp.access_token == "access.jwt.token"
        assert resp.refresh_token == "refresh.jwt.token"
        assert resp.token_type == "bearer"

    def test_default_token_type(self):
        resp = TokenResponse(
            access_token="access",
            refresh_token="refresh",
        )
        assert resp.token_type == "bearer"


class TestUserResponse:
    def test_valid_response(self):
        user_id = uuid.uuid4()
        resp = UserResponse(
            id=user_id,
            username="testuser",
            email="test@example.com",
            role="engineer",
            is_active=True,
            auth_provider="local",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert resp.id == user_id
        assert resp.role.value == "engineer"
        assert resp.tenant_id is None
