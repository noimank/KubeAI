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


async def _create_tenant(client: AsyncClient, headers: dict) -> dict:
    name = _unique("tenant")
    resp = await client.post(
        "/api/tenants",
        json={"name": name, "display_name": f"Tenant {name}"},
        headers=headers,
    )
    return resp.json()["data"]


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_create_tenant_success(
    mock_build, mock_s3, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers
):
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
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_list_tenants(mock_build, mock_s3, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
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


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_get_tenant_detail(
    mock_build, mock_s3, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers
):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.get(f"/api/tenants/{tenant_data['id']}", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["id"] == tenant_data["id"]
    assert body["data"]["name"] == tenant_data["name"]
    assert "member_count" in body["data"]


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_get_tenant_not_found(mock_enforce, client, admin_headers):
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/tenants/{fake_id}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_update_tenant(mock_build, mock_s3, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.put(
        f"/api/tenants/{tenant_data['id']}",
        json={"display_name": "Updated Name", "description": "Updated desc"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["display_name"] == "Updated Name"
    assert body["data"]["description"] == "Updated desc"


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_update_tenant_not_found(mock_enforce, client, admin_headers):
    fake_id = str(uuid.uuid4())
    response = await client.put(
        f"/api/tenants/{fake_id}",
        json={"display_name": "X"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_disable_tenant(mock_build, mock_s3, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.patch(
        f"/api/tenants/{tenant_data['id']}/status",
        json={"status": "disabled"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "disabled"


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_enable_tenant(mock_build, mock_s3, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    await client.patch(
        f"/api/tenants/{tenant_data['id']}/status",
        json={"status": "disabled"},
        headers=admin_headers,
    )

    response = await client.patch(
        f"/api/tenants/{tenant_data['id']}/status",
        json={"status": "active"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "active"


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_disable_already_disabled(
    mock_build, mock_s3, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers
):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    await client.patch(
        f"/api/tenants/{tenant_data['id']}/status",
        json={"status": "disabled"},
        headers=admin_headers,
    )

    response = await client.patch(
        f"/api/tenants/{tenant_data['id']}/status",
        json={"status": "disabled"},
        headers=admin_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.delete_namespace")
@patch("app.services.tenant_service.delete_network_policy")
@patch("app.services.tenant_service.delete_resource_quota")
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_delete_tenant_no_members(
    mock_build,
    mock_create_s3,
    mock_create_quota,
    mock_create_np,
    mock_create_ns,
    mock_del_quota,
    mock_del_np,
    mock_del_ns,
    mock_enforce,
    client,
    admin_headers,
):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.delete(f"/api/tenants/{tenant_data['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_delete_tenant_not_found(mock_enforce, client, admin_headers):
    fake_id = str(uuid.uuid4())
    response = await client.delete(f"/api/tenants/{fake_id}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_delete_tenant_with_members(
    mock_build, mock_s3, mock_quota, mock_np, mock_ns, mock_enforce, client, admin_headers
):
    mock_build.return_value = MagicMock()
    tenant_data = await _create_tenant(client, admin_headers)

    # Create a user and assign to tenant
    username = _unique("member")
    email = f"{username}@example.com"
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "Passw0rd", "confirm_password": "Passw0rd"},
    )
    from sqlalchemy import select as sa_select

    from app.core.database import async_session_factory
    from app.models.user import User

    async with async_session_factory() as db:
        result = await db.execute(sa_select(User).where(User.username == username))
        member = result.scalar_one()
        member.tenant_id = uuid.UUID(tenant_data["id"])
        await db.commit()

    response = await client.delete(f"/api/tenants/{tenant_data['id']}", headers=admin_headers)
    assert response.status_code == 409
    assert "请先移除" in response.json()["message"]


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.update_resource_quota")
@patch("app.services.tenant_service.get_quota_used")
@patch("app.services.tenant_service.get_cluster_capacity")
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_update_tenant_quota_success(
    mock_build,
    mock_create_s3,
    mock_create_quota,
    mock_create_np,
    mock_create_ns,
    mock_capacity,
    mock_used,
    mock_k8s_update,
    mock_enforce,
    client,
    admin_headers,
):
    mock_build.return_value = MagicMock()
    mock_capacity.return_value = {"gpu": "16", "cpu": "128", "memory": "512GiKi"}
    mock_used.return_value = {
        "requests.nvidia.com/gpu": "0",
        "requests.cpu": "0",
        "requests.memory": "0",
        "requests.storage": "0",
    }

    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.put(
        f"/api/tenants/{tenant_data['id']}/quota",
        json={"gpu_limit": 8, "cpu_limit": "32", "memory_limit": "64Gi", "storage_limit": "100Gi"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["gpu_limit"] == 8
    assert body["data"]["cpu_limit"] == "32"
    assert body["data"]["memory_limit"] == "64Gi"
    assert body["data"]["storage_limit"] == "100Gi"


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.get_quota_used")
@patch("app.services.tenant_service.get_cluster_capacity")
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_update_tenant_quota_exceeds_cluster(
    mock_build,
    mock_create_s3,
    mock_create_quota,
    mock_create_np,
    mock_create_ns,
    mock_capacity,
    mock_used,
    mock_enforce,
    client,
    admin_headers,
):
    mock_build.return_value = MagicMock()
    mock_capacity.return_value = {"gpu": "4", "cpu": "64", "memory": "256GiKi"}

    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.put(
        f"/api/tenants/{tenant_data['id']}/quota",
        json={"gpu_limit": 100, "cpu_limit": "32", "memory_limit": "64Gi", "storage_limit": "100Gi"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert "超过集群可分配余量" in response.json()["message"]


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.get_quota_used")
@patch("app.services.tenant_service.get_cluster_capacity")
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_update_tenant_quota_usage_exceeds(
    mock_build,
    mock_create_s3,
    mock_create_quota,
    mock_create_np,
    mock_create_ns,
    mock_capacity,
    mock_used,
    mock_enforce,
    client,
    admin_headers,
):
    mock_build.return_value = MagicMock()
    mock_capacity.return_value = {"gpu": "16", "cpu": "128", "memory": "512GiKi"}
    mock_used.return_value = {
        "requests.nvidia.com/gpu": "10",
        "requests.cpu": "2",
        "requests.memory": "4Gi",
        "requests.storage": "10Gi",
    }

    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.put(
        f"/api/tenants/{tenant_data['id']}/quota",
        json={"gpu_limit": 8, "cpu_limit": "32", "memory_limit": "64Gi", "storage_limit": "100Gi"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert "使用量" in response.json()["message"]


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.update_resource_quota")
@patch("app.services.tenant_service.get_quota_used")
@patch("app.services.tenant_service.get_cluster_capacity")
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_update_tenant_quota_force(
    mock_build,
    mock_create_s3,
    mock_create_quota,
    mock_create_np,
    mock_create_ns,
    mock_capacity,
    mock_used,
    mock_k8s_update,
    mock_enforce,
    client,
    admin_headers,
):
    mock_build.return_value = MagicMock()
    mock_capacity.return_value = {"gpu": "16", "cpu": "128", "memory": "512GiKi"}
    mock_used.return_value = {
        "requests.nvidia.com/gpu": "10",
        "requests.cpu": "2",
        "requests.memory": "4Gi",
        "requests.storage": "10Gi",
    }

    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.put(
        f"/api/tenants/{tenant_data['id']}/quota",
        json={"gpu_limit": 8, "cpu_limit": "32", "memory_limit": "64Gi", "storage_limit": "100Gi", "force": True},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["gpu_limit"] == 8


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.tenant_service.get_quota_used")
@patch("app.services.tenant_service.create_namespace")
@patch("app.services.tenant_service.create_resource_quota")
@patch("app.services.tenant_service.create_tenant_network_policy")
@patch("app.services.tenant_service.ensure_s3_credentials_secret")
@patch("app.services.tenant_service.build_tenant_resource_quota")
async def test_get_tenant_quota_usage(
    mock_build,
    mock_create_s3,
    mock_create_quota,
    mock_create_np,
    mock_create_ns,
    mock_used,
    mock_enforce,
    client,
    admin_headers,
):
    mock_build.return_value = MagicMock()
    mock_used.return_value = {
        "requests.nvidia.com/gpu": "3",
        "requests.cpu": "8",
        "requests.memory": "16Gi",
        "requests.storage": "50Gi",
    }

    tenant_data = await _create_tenant(client, admin_headers)

    response = await client.get(f"/api/tenants/{tenant_data['id']}/quota-usage", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["gpu_used"] == 3
    assert body["data"]["cpu_used"] == "8"


@pytest.mark.asyncio(loop_scope="session")
async def test_update_tenant_quota_unauthorized(client):
    response = await client.put(
        f"/api/tenants/{uuid.uuid4()}/quota",
        json={"gpu_limit": 8, "cpu_limit": "32", "memory_limit": "64Gi", "storage_limit": "100Gi"},
    )
    assert response.status_code == 401
