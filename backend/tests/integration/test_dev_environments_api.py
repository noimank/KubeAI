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
        user.tenant_id = None
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


class TestListDevEnvironments:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_list_requires_tenant_context(self, _, client: AsyncClient, admin_headers):
        resp = await client.get("/api/dev-environments", headers=admin_headers)
        assert resp.status_code == 403
        assert "租户上下文" in resp.json()["message"]


class TestDevEnvironmentPermission:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=False)
    async def test_create_without_permission(self, _, client: AsyncClient, admin_headers):
        resp = await client.post(
            "/api/dev-environments",
            json={"name": "test", "image": "jupyter/test:latest"},
            headers=admin_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=False)
    async def test_delete_requires_manage_permission(self, _, client: AsyncClient, admin_headers):
        resp = await client.delete(f"/api/dev-environments/{uuid.uuid4()}", headers=admin_headers)
        assert resp.status_code == 403


class TestDevEnvironmentCRUD:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("app.api.endpoints.dev_environments.enqueue_dev_environment_provision")
    @patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
    async def test_create_and_get_environment(self, _, mock_enqueue, client: AsyncClient, admin_headers):
        from app.core.database import async_session_factory
        from app.models.tenant import Tenant

        tenant_id = uuid.uuid4()
        tenant_namespace = f"kubeai-{_unique('ns')}"
        async with async_session_factory() as db:
            tenant = Tenant(
                name=_unique("tenant"),
                display_name="Test Tenant",
                k8s_namespace_name=tenant_namespace,
                gpu_limit=10,
            )
            tenant.id = tenant_id
            db.add(tenant)
            await db.commit()

            from sqlalchemy import select

            from app.models.user import User

            token = admin_headers["Authorization"].replace("Bearer ", "")
            from app.core.security import decode_token

            payload = decode_token(token)
            user_id = payload["sub"]
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one()
            user.tenant_id = tenant_id
            await db.commit()

        from app.models.dev_environment_image import DevEnvironmentImage

        image_id = uuid.uuid4()
        async with async_session_factory() as db:
            env_image = DevEnvironmentImage(
                name="jupyter-pytorch",
                image_ref="jupyter/pytorch:latest",
                environment_type="jupyter",
                is_enabled=True,
            )
            env_image.id = image_id
            env_image.tenant_id = tenant_id
            db.add(env_image)
            await db.commit()

        resp = await client.post(
            "/api/dev-environments",
            json={
                "name": "my-notebook",
                "environment_image_id": str(image_id),
                "cpu": "4",
                "memory": "8Gi",
                "gpu_count": 0,
                "description": "Test environment",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "my-notebook"
        assert data["status"] == "pending"
        env_id = data["id"]
        mock_enqueue.assert_called_once()
        assert str(mock_enqueue.call_args.args[0]) == env_id
        assert mock_enqueue.call_args.args[1] == tenant_id

        resp = await client.get(f"/api/dev-environments/{env_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == env_id
