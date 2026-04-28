import uuid

import pytest
from httpx import AsyncClient


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _register_and_get_token(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": _unique("user"),
            "email": f"{_unique('email')}@example.com",
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )
    return resp.json()["data"]["access_token"]


@pytest.mark.asyncio(loop_scope="session")
async def test_me_returns_role(client: AsyncClient):
    token = await _register_and_get_token(client)
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "role" in data
    assert data["role"] == "engineer"


@pytest.mark.asyncio(loop_scope="session")
async def test_me_returns_role_in_response(client: AsyncClient):
    token = await _register_and_get_token(client)
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = response.json()
    assert body["success"] is True
    assert body["data"]["role"] == "engineer"
