import uuid

import pytest
from httpx import AsyncClient


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
