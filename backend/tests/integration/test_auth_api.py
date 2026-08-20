import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.user import User as UserModel


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _register_user(client: AsyncClient, username: str | None = None, email: str | None = None):
    return await client.post(
        "/api/auth/register",
        json={
            "username": username or _unique("user"),
            "email": email or f"{_unique('email')}@example.com",
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_register_success(client):
    response = await client.post(
        "/api/auth/register",
        json={
            "username": _unique("newuser"),
            "email": f"{_unique('new')}@example.com",
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["access_token"] is not None
    assert body["data"]["refresh_token"] is not None
    assert body["data"]["token_type"] == "bearer"


@pytest.mark.asyncio(loop_scope="session")
async def test_auth_config_default(client):
    response = await client.get("/api/auth/config")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["app_name"] == settings.APP_NAME
    assert body["data"]["allow_user_registration"] is True
    assert body["data"]["oidc_auto_redirect"] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_auth_config_registration_disabled(client):
    with patch.object(settings, "ALLOW_USER_REGISTRATION", False):
        response = await client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json()["data"]["allow_user_registration"] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_register_duplicate_username(client):
    username = _unique("existing")
    await _register_user(client, username=username, email=f"{_unique('a')}@example.com")

    response = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{_unique('b')}@example.com",
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )
    assert response.status_code == 409
    assert "用户名" in response.json()["message"]


@pytest.mark.asyncio(loop_scope="session")
async def test_register_duplicate_email(client):
    email = f"{_unique('dup')}@example.com"
    await _register_user(client, username=_unique("a"), email=email)

    response = await client.post(
        "/api/auth/register",
        json={
            "username": _unique("b"),
            "email": email,
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )
    assert response.status_code == 409
    assert "邮箱" in response.json()["message"]


@pytest.mark.asyncio(loop_scope="session")
async def test_register_invalid_password(client):
    response = await client.post(
        "/api/auth/register",
        json={
            "username": _unique("badpw"),
            "email": f"{_unique('badpw')}@example.com",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_register_disabled(client):
    with patch("app.services.auth_service.settings") as mock_settings:
        mock_settings.ALLOW_USER_REGISTRATION = False
        response = await client.post(
            "/api/auth/register",
            json={
                "username": _unique("disabled"),
                "email": f"{_unique('disabled')}@example.com",
                "password": "Passw0rd",
                "confirm_password": "Passw0rd",
            },
        )

    assert response.status_code == 403
    assert response.json()["success"] is False
    assert "不允许用户自行注册" in response.json()["message"]


@pytest.mark.asyncio(loop_scope="session")
async def test_login_success(client):
    username = _unique("loginok")
    await _register_user(client, username=username, email=f"{username}@example.com")

    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "Passw0rd"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["access_token"] is not None
    assert body["data"]["refresh_token"] is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_login_wrong_password(client):
    username = _unique("badlogin")
    await _register_user(client, username=username, email=f"{username}@example.com")

    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "WrongPass1"},
    )
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_login_nonexistent_user(client):
    response = await client.post(
        "/api/auth/login",
        json={"username": "nouser_nouser", "password": "Passw0rd"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_login_locked_after_5_failures(client):
    username = _unique("lock")
    await _register_user(client, username=username, email=f"{username}@example.com")

    for i in range(5):
        resp = await client.post(
            "/api/auth/login",
            json={"username": username, "password": f"Wrong{i}Pass"},
        )
        assert resp.status_code == 401

    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "Passw0rd"},
    )
    assert response.status_code == 401
    assert "锁定" in response.json()["message"]


async def _convert_to_external(username: str) -> None:
    """将本地账号切换为第三方 (oidc) 登录账号, 模拟 OAuth 绑定后的用户."""
    async with async_session_factory() as db:
        await db.execute(
            update(UserModel)
            .where(UserModel.username == username)
            .values(auth_provider="oidc", external_id=f"ext-{username}")
        )
        await db.commit()


def _auth_headers(register_response) -> dict[str, str]:
    return {"Authorization": f"Bearer {register_response.json()['data']['access_token']}"}


@pytest.mark.asyncio(loop_scope="session")
async def test_me_returns_local_provider(client):
    headers = _auth_headers(await _register_user(client))

    response = await client.get("/api/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["auth_provider"] == "local"


@pytest.mark.asyncio(loop_scope="session")
async def test_me_returns_external_provider(client):
    username = _unique("oidc")
    headers = _auth_headers(await _register_user(client, username=username, email=f"{username}@example.com"))
    await _convert_to_external(username)

    response = await client.get("/api/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["auth_provider"] == "oidc"


@pytest.mark.asyncio(loop_scope="session")
async def test_local_user_can_update_profile(client):
    headers = _auth_headers(await _register_user(client))

    response = await client.patch(
        "/api/auth/me/profile",
        json={"nickname": "新昵称"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["nickname"] == "新昵称"


@pytest.mark.asyncio(loop_scope="session")
async def test_local_user_can_change_password(client):
    username = _unique("chpw")
    headers = _auth_headers(await _register_user(client, username=username, email=f"{username}@example.com"))

    response = await client.post(
        "/api/auth/me/password",
        json={
            "current_password": "Passw0rd",
            "new_password": "NewPassw0rd1",
            "confirm_password": "NewPassw0rd1",
        },
        headers=headers,
    )
    assert response.status_code == 200

    relogin = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "NewPassw0rd1"},
    )
    assert relogin.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_external_user_cannot_update_profile(client):
    username = _unique("oidcprof")
    headers = _auth_headers(await _register_user(client, username=username, email=f"{username}@example.com"))
    await _convert_to_external(username)

    response = await client.patch(
        "/api/auth/me/profile",
        json={"nickname": "新昵称"},
        headers=headers,
    )

    assert response.status_code == 403
    assert "第三方" in response.json()["message"]


@pytest.mark.asyncio(loop_scope="session")
async def test_external_user_cannot_change_password(client):
    username = _unique("oidcpw")
    headers = _auth_headers(await _register_user(client, username=username, email=f"{username}@example.com"))
    await _convert_to_external(username)

    response = await client.post(
        "/api/auth/me/password",
        json={
            "current_password": "Passw0rd",
            "new_password": "NewPassw0rd1",
            "confirm_password": "NewPassw0rd1",
        },
        headers=headers,
    )

    assert response.status_code == 403
    assert "第三方" in response.json()["message"]


@pytest.mark.asyncio(loop_scope="session")
async def test_external_user_cannot_upload_avatar(client):
    username = _unique("oidcava")
    headers = _auth_headers(await _register_user(client, username=username, email=f"{username}@example.com"))
    await _convert_to_external(username)

    response = await client.post(
        "/api/auth/me/avatar",
        files={"file": ("avatar.png", b"fake-png-bytes", "image/png")},
        headers=headers,
    )

    assert response.status_code == 403
    assert "第三方" in response.json()["message"]
