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


def _mock_minio():
    m = MagicMock()
    m.ensure_bucket = MagicMock()
    m.upload_stream = MagicMock()
    m.list_objects = MagicMock(return_value=[])
    m.delete_objects = MagicMock()
    return m


async def _create_tenant_with_user(client: AsyncClient, headers: dict) -> tuple[dict, str]:
    name = _unique("tenant")
    with (
        patch("app.services.tenant_service.create_namespace"),
        patch("app.services.tenant_service.create_resource_quota"),
        patch("app.services.tenant_service.create_tenant_network_policy"),
        patch("app.services.tenant_service.build_tenant_resource_quota", return_value=MagicMock()),
    ):
        resp = await client.post(
            "/api/tenants",
            json={"name": name, "display_name": f"Tenant {name}"},
            headers=headers,
        )
    tenant = resp.json()["data"]

    username = _unique("user")
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
        user.role = UserRole.ENGINEER
        user.tenant_id = uuid.UUID(tenant["id"])
        await db.commit()

    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "Passw0rd"},
    )
    token = resp.json()["data"]["access_token"]
    return tenant, token


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.endpoints.datasets.get_minio_client")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.dataset_service.asyncio.to_thread")
async def test_create_dataset(mock_to_thread, mock_enforce, mock_get_minio, client, admin_headers):
    mock_get_minio.return_value = _mock_minio()
    _tenant, token = await _create_tenant_with_user(client, admin_headers)
    user_headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/datasets",
        json={"name": "test-dataset", "description": "A test dataset"},
        headers=user_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == "test-dataset"
    assert body["data"]["description"] == "A test dataset"
    assert body["data"]["version_count"] == 0


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.endpoints.datasets.get_minio_client")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.dataset_service.asyncio.to_thread")
async def test_list_datasets(mock_to_thread, mock_enforce, mock_get_minio, client, admin_headers):
    mock_get_minio.return_value = _mock_minio()
    _tenant, token = await _create_tenant_with_user(client, admin_headers)
    user_headers = {"Authorization": f"Bearer {token}"}

    for i in range(3):
        await client.post(
            "/api/datasets",
            json={"name": f"dataset-{i}", "description": f"Dataset {i}"},
            headers=user_headers,
        )

    response = await client.get("/api/datasets", headers=user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] >= 3


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.endpoints.datasets.get_minio_client")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.dataset_service.asyncio.to_thread")
async def test_get_dataset_detail(mock_to_thread, mock_enforce, mock_get_minio, client, admin_headers):
    mock_get_minio.return_value = _mock_minio()
    _tenant, token = await _create_tenant_with_user(client, admin_headers)
    user_headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/datasets",
        json={"name": "detail-ds", "description": "For detail test"},
        headers=user_headers,
    )
    dataset_id = create_resp.json()["data"]["id"]

    response = await client.get(f"/api/datasets/{dataset_id}", headers=user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["name"] == "detail-ds"
    assert body["data"]["versions"] is not None


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.endpoints.datasets.get_minio_client")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.dataset_service.asyncio.to_thread")
async def test_create_version(mock_to_thread, mock_enforce, mock_get_minio, client, admin_headers):
    mock_get_minio.return_value = _mock_minio()
    _tenant, token = await _create_tenant_with_user(client, admin_headers)
    user_headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/datasets",
        json={"name": "version-ds", "description": "Version test"},
        headers=user_headers,
    )
    dataset_id = create_resp.json()["data"]["id"]

    version_resp = await client.post(
        f"/api/datasets/{dataset_id}/versions",
        json={"description": "First version"},
        headers=user_headers,
    )
    assert version_resp.status_code == 200
    body = version_resp.json()
    assert body["data"]["version_number"] == 1
    assert body["data"]["description"] == "First version"


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.endpoints.datasets.get_minio_client")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
@patch("app.services.dataset_service.asyncio.to_thread")
async def test_delete_dataset(mock_to_thread, mock_enforce, mock_get_minio, client, admin_headers):
    mock_get_minio.return_value = _mock_minio()
    _tenant, token = await _create_tenant_with_user(client, admin_headers)
    user_headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/datasets",
        json={"name": "delete-ds", "description": "To be deleted"},
        headers=user_headers,
    )
    dataset_id = create_resp.json()["data"]["id"]

    response = await client.delete(f"/api/datasets/{dataset_id}", headers=user_headers)
    assert response.status_code == 200

    get_resp = await client.get(f"/api/datasets/{dataset_id}", headers=user_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.endpoints.datasets.get_minio_client")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_list_datasets_with_keyword(mock_enforce, mock_get_minio, client, admin_headers):
    mock_get_minio.return_value = _mock_minio()
    _tenant, token = await _create_tenant_with_user(client, admin_headers)
    user_headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/datasets",
        json={"name": "unique-keyword-ds", "description": "test"},
        headers=user_headers,
    )
    await client.post(
        "/api/datasets",
        json={"name": "other-dataset", "description": "test"},
        headers=user_headers,
    )

    response = await client.get("/api/datasets?keyword=unique-keyword", headers=user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] >= 1
    assert any(ds["name"] == "unique-keyword-ds" for ds in body["data"]["items"])
