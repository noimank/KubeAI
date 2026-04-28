import uuid

import pytest
from httpx import AsyncClient


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _register_user(client: AsyncClient, username: str | None = None):
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": username or _unique("user"),
            "email": f"{_unique('email')}@example.com",
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )
    return resp.json()["data"]


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_success(client: AsyncClient):
    tokens = await _register_user(client)

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["access_token"] is not None
    assert body["data"]["refresh_token"] is not None
    assert body["data"]["token_type"] == "bearer"


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_with_invalid_token(client: AsyncClient):
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": "invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_with_access_token_fails(client: AsyncClient):
    tokens = await _register_user(client)

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_logout_revokes_token(client: AsyncClient):
    tokens = await _register_user(client)

    response = await client.post(
        "/api/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    me_response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_logout_without_refresh_token(client: AsyncClient):
    tokens = await _register_user(client)

    response = await client.post(
        "/api/auth/logout",
        json={},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_me_returns_user_info(client: AsyncClient):
    username = _unique("me")
    tokens = await _register_user(client, username=username)

    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["username"] == username
    assert body["data"]["email"] is not None
    assert body["data"]["is_active"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_me_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio(loop_scope="session")
async def test_me_with_invalid_token_returns_401(client: AsyncClient):
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_refreshed_token_is_new(client: AsyncClient):
    tokens = await _register_user(client)

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 200
    new_tokens = response.json()["data"]
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


@pytest.mark.asyncio(loop_scope="session")
async def test_old_refresh_token_revoked_after_refresh(client: AsyncClient):
    tokens = await _register_user(client)

    await client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 401
