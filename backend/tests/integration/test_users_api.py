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


async def _register_user(client: AsyncClient, **overrides) -> dict:
    username = overrides.get("username", _unique("user"))
    email = overrides.get("email", f"{username}@example.com")
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "Passw0rd", "confirm_password": "Passw0rd"},
    )
    from sqlalchemy import select as sa_select

    from app.core.database import async_session_factory
    from app.models.user import User

    async with async_session_factory() as db:
        result = await db.execute(sa_select(User).where(User.username == username))
        user = result.scalar_one()
        return {"id": str(user.id), "username": user.username}


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_list_users(mock_enforce, client, admin_headers):
    response = await client.get("/api/users", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"]["items"], list)
    assert "total" in body["data"]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_users_unauthorized(client):
    response = await client.get("/api/users")
    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_list_users_with_filters(mock_enforce, client, admin_headers):
    response = await client.get(
        "/api/users",
        params={"username": "nonexistent", "role": "admin", "is_active": True},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_get_user_detail(mock_enforce, client, admin_headers):
    user_data = await _register_user(client)

    response = await client.get(f"/api/users/{user_data['id']}", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["username"] == user_data["username"]
    assert "failed_login_attempts" in body["data"]


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_get_user_not_found(mock_enforce, client, admin_headers):
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/users/{fake_id}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_update_user_role(mock_enforce, client, admin_headers):
    user_data = await _register_user(client)

    response = await client.put(
        f"/api/users/{user_data['id']}",
        json={"role": "mlops"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["role"] == "mlops"


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_update_user_not_found(mock_enforce, client, admin_headers):
    fake_id = str(uuid.uuid4())
    response = await client.put(
        f"/api/users/{fake_id}",
        json={"role": "mlops"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_disable_user(mock_enforce, client, admin_headers):
    user_data = await _register_user(client)

    response = await client.patch(
        f"/api/users/{user_data['id']}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["is_active"] is False


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_enable_user(mock_enforce, client, admin_headers):
    user_data = await _register_user(client)

    await client.patch(
        f"/api/users/{user_data['id']}/status",
        json={"is_active": False},
        headers=admin_headers,
    )

    response = await client.patch(
        f"/api/users/{user_data['id']}/status",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is True


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_disable_already_disabled(mock_enforce, client, admin_headers):
    user_data = await _register_user(client)

    await client.patch(
        f"/api/users/{user_data['id']}/status",
        json={"is_active": False},
        headers=admin_headers,
    )

    response = await client.patch(
        f"/api/users/{user_data['id']}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_delete_user(mock_enforce, client, admin_headers):
    user_data = await _register_user(client)

    response = await client.delete(f"/api/users/{user_data['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_delete_user_not_found(mock_enforce, client, admin_headers):
    fake_id = str(uuid.uuid4())
    response = await client.delete(f"/api/users/{fake_id}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_deleted_user_not_in_list(mock_enforce, client, admin_headers):
    user_data = await _register_user(client)

    await client.delete(f"/api/users/{user_data['id']}", headers=admin_headers)

    response = await client.get("/api/users", headers=admin_headers)
    body = response.json()
    usernames = [u["username"] for u in body["data"]["items"]]
    assert user_data["username"] not in usernames


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_disabled_user_blocked_on_login(mock_enforce, client, admin_headers):
    username = _unique("disabled")
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
        user = result.scalar_one()
        user_id = user.id

    # Disable the user
    await client.patch(
        f"/api/users/{user_id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )

    # Try login — should fail with 403 (ForbiddenException)
    resp = await client.post("/api/auth/login", json={"username": username, "password": "Passw0rd"})
    assert resp.status_code == 403
    assert "禁用" in resp.json()["message"]
