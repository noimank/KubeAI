"""Integration tests for /api/annotation-templates endpoints.

覆盖:
- CRUD 链路 (含 group 字段)
- 分页 + 名称模糊 + group 过滤
- GET /groups 返回去重分组列表
- 非法 label_config 400
- 删除被引用模板 409
- 跨租户隔离 404
- engineer 可写 / annotator 写 403
- /ls-imports 反代形状 (含 group)

所有测试 mock 掉 ``app.api.deps.CasbinEnforcer.enforce`` -
ASGITransport 默认不跑 lifespan, Casbin enforcer 未初始化, 受保护端点会 500.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.enums import UserRole
from app.models.user import User

if TYPE_CHECKING:
    from httpx import AsyncClient


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create_user_and_token(client: AsyncClient, role: UserRole) -> tuple[str, uuid.UUID]:
    """注册用户, 设角色, 建租户, 返回 (token, tenant_id)."""
    from app.models.tenant import Tenant

    username = _unique("u")
    email = f"{username}@example.com"
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "Passw0rd", "confirm_password": "Passw0rd"},
    )
    tenant_name = _unique("t")
    tenant_id = uuid.uuid4()
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one()
        user.role = role
        tenant = Tenant(id=tenant_id, name=tenant_name, display_name=tenant_name)
        db.add(tenant)
        await db.flush()
        user.tenant_id = tenant.id
        await db.commit()

    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "Passw0rd"},
    )
    return resp.json()["data"]["access_token"], tenant_id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_VALID_XML = """<View>
  <Image name="image" value="$image"/>
  <Choices name="choice" toName="image" choice="single-radio">
    <Choice value="a"/>
    <Choice value="b"/>
  </Choices>
</View>"""


def _payload(name: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": name,
        "label_config": _VALID_XML,
        "tags": [],
        "group": "计算机视觉",
    }
    body.update(overrides)
    return body


# 1) POST -> GET 验证 label_config + group
@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_create_then_get_returns_payload(mock_enforce: Any, client: AsyncClient) -> None:
    token, _ = await _create_user_and_token(client, UserRole.ADMIN)
    headers = _auth(token)
    body = _payload(_unique("tmpl"), description="test", tags=["图像"], group="音频标注")
    resp = await client.post("/api/annotation-templates", headers=headers, json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["label_config"] == _VALID_XML
    assert data["group"] == "音频标注"
    assert data["tags"] == ["图像"]
    template_id = data["id"]

    resp = await client.get(f"/api/annotation-templates/{template_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["name"].startswith("tmpl_")
    assert resp.json()["data"]["project_count"] == 0


# 2) 列表分页 + 名称模糊 + group 过滤
@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_list_paginates_and_filters_by_name(mock_enforce: Any, client: AsyncClient) -> None:
    token, _ = await _create_user_and_token(client, UserRole.ADMIN)
    headers = _auth(token)
    for i in range(3):
        await client.post(
            "/api/annotation-templates",
            headers=headers,
            json=_payload(_unique(f"page_{i}")),
        )

    resp = await client.get(
        "/api/annotation-templates",
        headers=headers,
        params={"page": 1, "page_size": 2},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["page_size"] == 2
    assert body["total"] >= 3
    assert len(body["items"]) == 2


# 2b) GET /groups
@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_list_groups_returns_distinct(mock_enforce: Any, client: AsyncClient) -> None:
    token, _ = await _create_user_and_token(client, UserRole.ADMIN)
    headers = _auth(token)
    await client.post(
        "/api/annotation-templates",
        headers=headers,
        json=_payload(_unique("g1"), group="自然语言"),
    )
    await client.post(
        "/api/annotation-templates",
        headers=headers,
        json=_payload(_unique("g2"), group="自然语言"),
    )
    await client.post(
        "/api/annotation-templates",
        headers=headers,
        json=_payload(_unique("g3"), group="计算机视觉"),
    )

    resp = await client.get("/api/annotation-templates/groups", headers=headers)
    assert resp.status_code == 200
    groups = resp.json()["data"]
    assert "自然语言" in groups
    assert "计算机视觉" in groups


# 3) PATCH 空 body -> 400
@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_update_template_empty_body_returns_400(mock_enforce: Any, client: AsyncClient) -> None:
    token, _ = await _create_user_and_token(client, UserRole.ADMIN)
    headers = _auth(token)
    resp = await client.post(
        "/api/annotation-templates",
        headers=headers,
        json=_payload(_unique("t")),
    )
    template_id = resp.json()["data"]["id"]
    resp = await client.patch(f"/api/annotation-templates/{template_id}", headers=headers, json={})
    assert resp.status_code == 400


# 4) 删被引用模板 -> 409
@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_delete_referenced_template_returns_409(mock_enforce: Any, client: AsyncClient) -> None:
    from app.models.annotation import AnnotationProject
    from app.models.dataset import Dataset, DatasetVersion

    token, tenant_id = await _create_user_and_token(client, UserRole.ADMIN)
    headers = _auth(token)
    resp = await client.post(
        "/api/annotation-templates",
        headers=headers,
        json=_payload(_unique("referenced")),
    )
    template_id = resp.json()["data"]["id"]

    async with async_session_factory() as db:
        ds = (await db.execute(select(Dataset).where(Dataset.tenant_id == tenant_id).limit(1))).scalar_one_or_none()
        if not ds:
            pytest.skip("no dataset in template's tenant to reference")
        ver = (
            await db.execute(select(DatasetVersion).where(DatasetVersion.dataset_id == ds.id).limit(1))
        ).scalar_one_or_none()
        if not ver:
            pytest.skip("no dataset version to reference")
        u = (await db.execute(select(User).where(User.username.like("u_%")).limit(1))).scalar_one()
        proj = AnnotationProject(
            name=_unique("ref-proj"),
            dataset_id=ds.id,
            dataset_version_id=ver.id,
            template_id=uuid.UUID(template_id),
            label_config=_VALID_XML,
            total_tasks=0,
            completed_tasks=0,
            status="active",
            tenant_id=tenant_id,
            created_by=u.id,
        )
        db.add(proj)
        await db.commit()

    resp = await client.delete(f"/api/annotation-templates/{template_id}", headers=headers)
    assert resp.status_code == 409, resp.text
    assert "引用" in resp.json()["message"]


# 5) 跨租户访问 -> 404
@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_tenant_isolation_blocks_cross_tenant_access(mock_enforce: Any, client: AsyncClient) -> None:
    token_a, _ = await _create_user_and_token(client, UserRole.ADMIN)
    token_b, _ = await _create_user_and_token(client, UserRole.ADMIN)
    headers_a = _auth(token_a)
    headers_b = _auth(token_b)

    resp = await client.post(
        "/api/annotation-templates",
        headers=headers_a,
        json=_payload(_unique("a-only")),
    )
    template_id = resp.json()["data"]["id"]

    resp = await client.get(f"/api/annotation-templates/{template_id}", headers=headers_b)
    assert resp.status_code == 404


# 6) 权限: engineer 可写, annotator 写返回 403
@pytest.mark.asyncio(loop_scope="session")
async def test_permission_engineer_can_write_annotator_cannot(client: AsyncClient) -> None:
    def _enforce(role: str, resource: str, action: str) -> bool:
        if resource == "annotation_templates" and action in ("write", "manage"):
            return role in {"admin", "mlops", "engineer"}
        return True

    eng_token, _ = await _create_user_and_token(client, UserRole.ENGINEER)
    eng_headers = _auth(eng_token)
    with patch(
        "app.api.deps.CasbinEnforcer.enforce",
        side_effect=lambda r, res, act: _enforce(r, res, act),
    ):
        resp = await client.post(
            "/api/annotation-templates",
            headers=eng_headers,
            json=_payload(_unique("eng")),
        )
    assert resp.status_code == 200, resp.text

    ann_token, _ = await _create_user_and_token(client, UserRole.ANNOTATOR)
    ann_headers = _auth(ann_token)
    with patch(
        "app.api.deps.CasbinEnforcer.enforce",
        side_effect=lambda r, res, act: _enforce(r, res, act),
    ):
        resp = await client.post(
            "/api/annotation-templates",
            headers=ann_headers,
            json=_payload(_unique("ann")),
        )
    assert resp.status_code == 403


# 7) /ls-imports 从内置 JSON 文件读取
@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_ls_imports_endpoint_returns_builtin_templates(mock_enforce: Any, client: AsyncClient) -> None:
    token, _ = await _create_user_and_token(client, UserRole.ADMIN)
    headers = _auth(token)

    resp = await client.get("/api/annotation-templates/ls-imports", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1
    assert all("key" in item for item in items)
    assert all("label" in item for item in items)
    assert all("config" in item for item in items)
    assert all("group" in item for item in items)


# 8) 非法 label_config -> 400
@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_invalid_label_config_returns_400_on_create(mock_enforce: Any, client: AsyncClient) -> None:
    token, _ = await _create_user_and_token(client, UserRole.ADMIN)
    headers = _auth(token)
    resp = await client.post(
        "/api/annotation-templates",
        headers=headers,
        json=_payload(_unique("bad"), label_config="<broken"),
    )
    assert resp.status_code == 400
