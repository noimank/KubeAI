import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _get_admin_token(client: AsyncClient) -> str:
    username = _unique("admin")
    email = f"{username}@example.com"
    await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "Passw0rd",
            "confirm_password": "Passw0rd",
        },
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


async def _create_image(client: AsyncClient, headers: dict, **overrides) -> dict:
    defaults = {
        "name": _unique("pytorch"),
        "tag": "2.1.0-cuda12.1",
        "image_ref": f"{_unique('img')}/pytorch:2.1.0-cuda12.1",
        "category": "training",
    }
    defaults.update(overrides)
    resp = await client.post("/api/images", json=defaults, headers=headers)
    assert resp.status_code == 200
    return resp.json()["data"]


class TestCreateImage:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_create_image_success(self, _, client: AsyncClient, admin_headers):
        resp = await client.post(
            "/api/images",
            json={
                "name": "pytorch-2.1",
                "tag": "2.1.0-cuda12.1",
                "image_ref": f"{_unique('img')}/pytorch:2.1.0",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "pytorch-2.1"
        assert data["source"] == "preset"
        assert data["is_enabled"] is True

    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=False)
    async def test_create_image_requires_manage_permission(self, _, client: AsyncClient, admin_headers):
        username = _unique("engineer")
        email = f"{username}@example.com"
        await client.post(
            "/api/auth/register",
            json={
                "username": username,
                "email": email,
                "password": "Passw0rd",
                "confirm_password": "Passw0rd",
            },
        )
        resp = await client.post(
            "/api/auth/login",
            json={"username": username, "password": "Passw0rd"},
        )
        engineer_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

        resp = await client.post(
            "/api/images",
            json={
                "name": "test",
                "tag": "1.0",
                "image_ref": f"{_unique('test')}/img:1.0",
            },
            headers=engineer_headers,
        )
        assert resp.status_code == 403


class TestListImages:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_list_images(self, _, client: AsyncClient, admin_headers):
        await _create_image(client, admin_headers)

        resp = await client.get("/api/images", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_list_images_with_keyword(self, _, client: AsyncClient, admin_headers):
        await _create_image(client, admin_headers, name="uniquekeywordtest")

        resp = await client.get(
            "/api/images",
            params={"keyword": "uniquekeywordtest"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert any("uniquekeywordtest" in img["name"] for img in data["items"])

    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_list_images_with_source_filter(self, _, client: AsyncClient, admin_headers):
        resp = await client.get(
            "/api/images",
            params={"source": "preset"},
            headers=admin_headers,
        )
        assert resp.status_code == 200


class TestGetImage:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_get_image(self, _, client: AsyncClient, admin_headers):
        image = await _create_image(client, admin_headers)

        resp = await client.get(f"/api/images/{image['id']}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == image["id"]

    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_get_image_not_found(self, _, client: AsyncClient, admin_headers):
        resp = await client.get(f"/api/images/{uuid.uuid4()}", headers=admin_headers)
        assert resp.status_code == 404


class TestUpdateImage:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_update_image(self, _, client: AsyncClient, admin_headers):
        image = await _create_image(client, admin_headers)

        resp = await client.put(
            f"/api/images/{image['id']}",
            json={"name": "updated-name"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "updated-name"


class TestDeleteImage:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_delete_image(self, _, client: AsyncClient, admin_headers):
        image = await _create_image(client, admin_headers)

        resp = await client.delete(f"/api/images/{image['id']}", headers=admin_headers)
        assert resp.status_code == 200

        resp = await client.get(f"/api/images/{image['id']}", headers=admin_headers)
        assert resp.status_code == 404


class TestToggleImage:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_toggle_image(self, _, client: AsyncClient, admin_headers):
        image = await _create_image(client, admin_headers)
        assert image["is_enabled"] is True

        resp = await client.patch(f"/api/images/{image['id']}/toggle", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_enabled"] is False

        resp = await client.patch(f"/api/images/{image['id']}/toggle", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_enabled"] is True


class TestBuildImageEndpoint:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.services.image_service.k8s_job")
    @patch("app.services.image_service.k8s_secret")
    @patch("app.services.image_service.get_harbor_client")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_build_image_no_tenant(
        self, _, mock_get_harbor, mock_secret, mock_job, client: AsyncClient, admin_headers
    ):
        """Admin without tenant_id should get 403 when trying to build"""
        resp = await client.post(
            "/api/images/build",
            json={
                "dockerfile": "FROM python:3.12",
                "name": "test-build",
                "tag": "v1",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 403


class TestGetBuildLogEndpoint:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_get_build_log_preset_image(self, _, client: AsyncClient, admin_headers):
        """Preset images should return empty log"""
        image = await _create_image(client, admin_headers)

        resp = await client.get(f"/api/images/{image['id']}/build-log", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["log"] == ""


class TestListSelectableImages:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_selectable_requires_tenant(self, _, client: AsyncClient, admin_headers):
        """Admin without tenant_id should get 403"""
        resp = await client.get("/api/images/selectable", headers=admin_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=False)
    async def test_selectable_requires_permission(self, _, client: AsyncClient, admin_headers):
        """User without images:read permission should get 403"""
        resp = await client.get("/api/images/selectable", headers=admin_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_selectable_success_with_tenant(self, _, client: AsyncClient, admin_headers):
        """User with tenant_id should get selectable images"""
        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.models.tenant import Tenant
        from app.models.user import User

        async with async_session_factory() as db:
            result = await db.execute(select(User).order_by(User.created_at.desc()).limit(1))
            user = result.scalar_one()

            tenant = Tenant(
                name=_unique("tenant"),
                display_name="Test Tenant",
                k8s_namespace_name=f"kubeai-test-{uuid.uuid4().hex[:8]}",
                cpu_limit="10",
                memory_limit="20Gi",
                gpu_limit=5,
                storage_limit="100Gi",
            )
            db.add(tenant)
            await db.flush()
            await db.refresh(tenant)

            user.tenant_id = tenant.id
            await db.commit()

        try:
            resp = await client.get("/api/images/selectable", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert isinstance(data["data"], list)
        finally:
            async with async_session_factory() as db:
                result = await db.execute(select(User).where(User.id == user.id))
                u = result.scalar_one()
                u.tenant_id = None
                await db.commit()
