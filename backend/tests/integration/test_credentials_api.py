import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.main import app
from app.models.enums import UserRole
from app.models.user import User


def _make_user(tenant_id: uuid.UUID | None = None, role: UserRole = UserRole.ENGINEER):
    return User(
        username="testuser",
        email="test@example.com",
        hashed_password="hash",
        tenant_id=tenant_id,
        role=role,
    )


@pytest.fixture
def mock_credential_service():
    with patch("app.api.endpoints.credentials._credential_service") as mock:
        mock.store_credential = AsyncMock(return_value="test-secret")
        mock.delete_credential = AsyncMock()
        yield mock


@pytest.fixture
def mock_tenant_name():
    with patch("app.api.endpoints.credentials._get_tenant_name", new=AsyncMock(return_value="test-tenant")):
        yield


@pytest.fixture
def override_user():
    user = None

    def _set(u):
        nonlocal user
        user = u

    async def _dependency():
        return user

    app.dependency_overrides[get_current_user] = _dependency
    yield _set
    app.dependency_overrides.clear()


class TestCreateCredential:
    @pytest.mark.asyncio
    async def test_create_credential_success(self, mock_credential_service, mock_tenant_name, override_user):
        tenant_id = uuid.uuid4()
        override_user(_make_user(tenant_id=tenant_id))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/credentials",
                json={"name": "db-password", "type": "password", "data": {"value": "secret123"}},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "db-password"
        mock_credential_service.store_credential.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_credential_no_tenant(self, mock_credential_service, mock_tenant_name, override_user):
        override_user(_make_user(tenant_id=None))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/credentials",
                json={"name": "db-password", "type": "password", "data": {"value": "secret123"}},
            )

        assert response.status_code == 403


class TestDeleteCredential:
    @pytest.mark.asyncio
    async def test_delete_credential_success(self, mock_credential_service, mock_tenant_name, override_user):
        tenant_id = uuid.uuid4()
        override_user(_make_user(tenant_id=tenant_id))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/api/credentials/db-password")

        assert response.status_code == 200
        mock_credential_service.delete_credential.assert_called_once()
