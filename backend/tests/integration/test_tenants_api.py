import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _get_admin_token(client: AsyncClient) -> str:
    username = _unique("admin")
    email = f"{username}@example.com"
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "Passw0rd", "confirm_password": "Passw0rd"},
    )
    from sqlalchemy import select

    from app.core.database import async_session_factory
    from app.models.enums import UserRole
    from app.models.user import User

    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one()
        user.role = UserRole.ADMIN
        await db.commit()

    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "Passw0rd"},
    )
    return resp.json()["data"]["access_token"]


@pytest.fixture
def admin_headers(client):
    import asyncio

    token = asyncio.get_event_loop().run_until_complete(_get_admin_token(client))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_create_tenant_success(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    name = _unique("tenant")

    response = await client.post(
        "/api/tenants",
        json={"name": name, "display_name": "Test Tenant"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == name
    assert body["data"]["gpu_limit"] == 0
    assert body["data"]["cpu_limit"] == "4"
    assert body["data"]["memory_limit"] == "8Gi"


@pytest.mark.asyncio(loop_scope="session")
async def test_create_tenant_unauthorized(client):
    response = await client.post(
        "/api/tenants",
        json={"name": "test", "display_name": "Test"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_list_tenants(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    name = _unique("tenant")

    await client.post(
        "/api/tenants",
        json={"name": name, "display_name": "Test Tenant"},
        headers=admin_headers,
    )

    response = await client.get("/api/tenants", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] >= 1
    assert isinstance(body["data"]["items"], list)


@pytest.mark.asyncio(loop_scope="session")
async def test_list_tenants_unauthorized(client):
    response = await client.get("/api/tenants")
    assert response.status_code == 401
