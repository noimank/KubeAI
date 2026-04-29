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


async def _create_tenant(client: AsyncClient, headers: dict) -> dict:
    name = _unique("tenant")
    resp = await client.post(
        "/api/tenants",
        json={"name": name, "display_name": f"Tenant {name}"},
        headers=headers,
    )
    return resp.json()["data"]


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
async def test_create_invitation(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.post(
        f"/api/tenants/{tenant_data['id']}/invitations",
        json={"email": "invite@example.com", "role": "engineer"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == "invite@example.com"
    assert body["data"]["role"] == "engineer"
    assert body["data"]["status"] == "pending"
    assert body["data"]["token"] is not None


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_list_invitations(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    await client.post(
        f"/api/tenants/{tenant_data['id']}/invitations",
        json={"email": "user1@example.com", "role": "engineer"},
        headers=admin_headers,
    )

    response = await client.get(
        f"/api/tenants/{tenant_data['id']}/invitations",
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) >= 1


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_cancel_invitation(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    create_resp = await client.post(
        f"/api/tenants/{tenant_data['id']}/invitations",
        json={"email": "cancel@example.com", "role": "mlops"},
        headers=admin_headers,
    )
    invitation_id = create_resp.json()["data"]["id"]

    response = await client.delete(
        f"/api/tenants/{tenant_data['id']}/invitations/{invitation_id}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_get_invitation_info(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    create_resp = await client.post(
        f"/api/tenants/{tenant_data['id']}/invitations",
        json={"email": "info@example.com", "role": "annotator"},
        headers=admin_headers,
    )
    token = create_resp.json()["data"]["token"]

    response = await client.get(f"/api/auth/invitation-info?token={token}")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == "info@example.com"
    assert body["data"]["role"] == "annotator"
    assert body["data"]["tenant_name"] == tenant_data["name"]


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_accept_invitation_new_user(
    mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers
):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    invite_email = f"{_unique('newuser')}@example.com"
    create_resp = await client.post(
        f"/api/tenants/{tenant_data['id']}/invitations",
        json={"email": invite_email, "role": "engineer"},
        headers=admin_headers,
    )
    token = create_resp.json()["data"]["token"]

    response = await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": token,
            "username": _unique("newuser"),
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["access_token"] is not None


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_list_members(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.get(
        f"/api/tenants/{tenant_data['id']}/members",
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_update_member_role(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    # Create member user and assign to tenant
    member_username = _unique("member")
    member_email = f"{member_username}@example.com"
    await client.post(
        "/api/auth/register",
        json={
            "username": member_username,
            "email": member_email,
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )
    from sqlalchemy import select as sa_select

    from app.core.database import async_session_factory
    from app.models.user import User

    async with async_session_factory() as db:
        result = await db.execute(sa_select(User).where(User.username == member_username))
        member = result.scalar_one()
        member.tenant_id = uuid.UUID(tenant_data["id"])
        await db.commit()
        member_id = member.id

    response = await client.patch(
        f"/api/tenants/{tenant_data['id']}/members/{member_id}/role",
        json={"role": "mlops"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["role"] == "mlops"


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_remove_member(mock_build, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    # Create and assign member
    member_username = _unique("remove")
    member_email = f"{member_username}@example.com"
    await client.post(
        "/api/auth/register",
        json={
            "username": member_username,
            "email": member_email,
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
    )
    from sqlalchemy import select as sa_select

    from app.core.database import async_session_factory
    from app.models.user import User

    async with async_session_factory() as db:
        result = await db.execute(sa_select(User).where(User.username == member_username))
        member = result.scalar_one()
        member.tenant_id = uuid.UUID(tenant_data["id"])
        await db.commit()
        member_id = member.id

    response = await client.delete(
        f"/api/tenants/{tenant_data['id']}/members/{member_id}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Verify member is removed (tenant_id is None)
    async with async_session_factory() as db:
        result = await db.execute(sa_select(User).where(User.id == member_id))
        removed_user = result.scalar_one()
        assert removed_user.tenant_id is None


@pytest.mark.asyncio(loop_scope="session")
async def test_invitation_info_invalid_token(client):
    response = await client.get("/api/auth/invitation-info?token=invalid-token")
    assert response.status_code == 400


@pytest.mark.asyncio(loop_scope="session")
async def test_accept_invitation_invalid_token(client):
    response = await client.post(
        "/api/auth/accept-invitation",
        json={"token": "invalid-token"},
    )
    assert response.status_code == 400
