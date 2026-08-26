import asyncio
import os
import sys
from contextlib import suppress

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 必须在导入 app 之前注入: Settings 会在 DEBUG=false 且 SECRET_KEY 为公开默认值时
# 拒绝启动 (生产 fail-fast), 测试环境固定使用独立随机密钥, 不受本机 .env 影响。
os.environ.setdefault("SECRET_KEY", "5f2a9c1e7b3d4f608a9b2c4d6e8f0a1c3b5d7e9f1a2c4b6d8e0f2a4c6b8d0e2f")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.database import async_session_factory
from app.main import app
from app.models.base import Base


@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# Reserve tables that must never be truncated:
#   alembic_version — alembic 迁移状态,清掉会导致 schema 失忆
#   casbin_rule     — RBAC 策略由 startup events.seed 加载,清掉会全 RBAC 失效
_PROTECTED_TABLES = {"alembic_version", "casbin_rule"}


def _purge_tenants_test_tables() -> None:
    """清空测试数据库中受 tenants FK 影响的所有表。

    表名从 SQLAlchemy metadata 动态读取,避免硬编码遗漏或拼错。
    users.tenant_id FK → tenants.id 是 nullable 但无 ondelete,直接
    TRUNCATE 会被 FK 引用阻塞;先 UPDATE 置 NULL,再 TRUNCATE。
    其余 FK 多为 CASCADE/SET NULL,TRUNCATE ... CASCADE 自动级联。
    """
    target_tables = sorted(t.name for t in Base.metadata.sorted_tables if t.name not in _PROTECTED_TABLES)

    async def _purge() -> None:
        async with async_session_factory() as db:
            await db.execute(text("UPDATE users SET tenant_id = NULL WHERE tenant_id IS NOT NULL"))
            await db.execute(text("TRUNCATE TABLE " + ", ".join(target_tables) + " RESTART IDENTITY CASCADE"))
            await db.commit()

    with suppress(ProgrammingError):
        # 表未创建(如首次运行前清库)— 跳过,首次测试会自然创建
        asyncio.get_event_loop().run_until_complete(_purge())


@pytest.fixture(autouse=True)
def _isolate_tenants_db(request: pytest.FixtureRequest) -> None:
    """仅在 test_tenants_api.py 模块的测试前清库。

    此前该测试因历次运行的租户累积导致 cluster_gpu 被透支,
    available_gpu 算成负数,任意 gpu_limit > 0 都触发
    QuotaExceededException → 422。fixture 仅作用于该模块避免
    干扰其他依赖顺序的集成测试。
    """
    if request.node.fspath.basename != "test_tenants_api.py":
        return
    _purge_tenants_test_tables()
