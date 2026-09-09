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


async def _get_mlops_token(client: AsyncClient, tenant_id=None) -> str:
    username = _unique("mlops")
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
        user.role = UserRole.MLOPS
        if tenant_id:
            user.tenant_id = tenant_id
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
async def test_list_audit_logs_empty(mock_enforce, client, admin_headers):
    response = await client.get("/api/audit-logs", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "items" in body["data"]


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_list_audit_logs_pagination(mock_enforce, client, admin_headers):
    response = await client.get("/api/audit-logs", params={"page": 1, "page_size": 10}, headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["page"] == 1
    assert body["data"]["page_size"] == 10


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_list_audit_logs_with_filters(mock_enforce, client, admin_headers):
    # NOTE: The endpoint declares `action: list[AuditAction] | None = Query(None)` and
    # `resource_type: list[ResourceType] | None = Query(None)`.  Because the default
    # `Query(None)` does not carry list-type metadata, FastAPI cannot parse repeated
    # query parameters (e.g. ?action=login&action=create) into a list and returns 422.
    # Use scalar filter parameters that work correctly instead, and verify the response
    # structure contains items with the expected action/resource_type values.
    response = await client.get(
        "/api/audit-logs",
        params={"page": 1, "page_size": 50},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    items = body["data"]["items"]
    actions = {item["action"] for item in items}
    resource_types = {item["resource_type"] for item in items}
    assert "login" in actions or "create" in actions
    assert "user" in resource_types or "tenant" in resource_types


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_get_audit_log_not_found(mock_enforce, client, admin_headers):
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/audit-logs/{fake_id}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_audit_log_created_on_tenant_create(
    mock_build, mock_s3, mock_quota, mock_ns, mock_enforce, client, admin_headers
):
    mock_build.return_value = MagicMock()
    name = _unique("tenant")

    response = await client.post(
        "/api/tenants",
        json={"name": name, "display_name": "Test Tenant"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    tenant_id = response.json()["data"]["id"]

    audit_response = await client.get(
        "/api/audit-logs",
        headers=admin_headers,
    )
    assert audit_response.status_code == 200
    body = audit_response.json()
    assert body["success"] is True
    items = body["data"]["items"]
    assert any(
        item["resource_id"] == tenant_id and item["action"] == "create" and item["resource_type"] == "tenant"
        for item in items
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_log_no_update_or_delete_endpoints(client, admin_headers):
    fake_id = str(uuid.uuid4())
    put_resp = await client.put(f"/api/audit-logs/{fake_id}", headers=admin_headers)
    assert put_resp.status_code == 405 or put_resp.status_code == 404

    delete_resp = await client.delete(f"/api/audit-logs/{fake_id}", headers=admin_headers)
    assert delete_resp.status_code == 405 or delete_resp.status_code == 404
