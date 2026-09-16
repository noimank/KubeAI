import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 必须在导入 app 之前注入: Settings 会在 DEBUG=false 且 SECRET_KEY 为公开默认值时
# 拒绝启动 (生产 fail-fast), 测试环境固定使用独立随机密钥, 不受本机 .env 影响。
os.environ.setdefault("SECRET_KEY", "5f2a9c1e7b3d4f608a9b2c4d6e8f0a1c3b5d7e9f1a2c4b6d8e0f2a4c6b8d0e2f")

# 测试专用数据库: 设置了 TEST_DATABASE_URL 就整条替换 DATABASE_URL, 保证测试
# (test_tenants_api 前置会 TRUNCATE 几乎全部表) 永远碰不到 .env 指向的开发库。
# 替换必须在导入 app 之前完成 — async_engine 在 import 时即已创建, 事后 patch 无效。
# 取值: 真实环境变量优先, 其次 backend/.env (pydantic-settings 读 .env 后不会回写
# os.environ, 而 conftest 早于 Settings 初始化, 这里补齐同语义)。
# 库名必须以 _test 结尾, 防止误填开发/生产库地址; 未设置时由 _ensure_test_db 拒绝连库测试。
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or dotenv_values(
    Path(__file__).resolve().parent.parent / ".env"
).get("TEST_DATABASE_URL")
if _TEST_DB_URL:
    _test_db_name = make_url(_TEST_DB_URL).database or ""
    if not _test_db_name.endswith("_test"):
        raise RuntimeError(
            f"TEST_DATABASE_URL 必须指向以 _test 结尾的专用测试库 (当前: {_test_db_name!r}), "
            "拒绝运行以免测试清掉误指数据库的数据"
        )
    os.environ["DATABASE_URL"] = _TEST_DB_URL

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import async_engine, async_session_factory
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
async def _ensure_test_db():
    """保证专用测试库存在且含全部表; 未配置 TEST_DATABASE_URL 时拒绝连库测试。

    库不存在 → 连同实例的 postgres 维护库自动 CREATE DATABASE; 表由
    Base.metadata.create_all 自建 (app 内无任何 create_all, 开发库全靠
    alembic 迁移, 专用测试库必须自足)。不 seed admin/casbin — 由测试自理。
    """
    if not _TEST_DB_URL:
        pytest.fail(
            "该测试需要连接数据库: 必须显式设置 TEST_DATABASE_URL 指向专用测试库 "
            "(库名以 _test 结尾, 库和表不存在会自动创建), 例如 "
            "TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/kubeai_test。"
            "不会回落到 .env 的 DATABASE_URL — 清库类测试会毁掉其中的数据。",
            pytrace=False,
        )
    url = make_url(_TEST_DB_URL)
    # CREATE DATABASE 不能在事务内执行, 维护连接固定用 AUTOCOMMIT
    maintenance = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with maintenance.connect() as conn:
            exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database})
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await maintenance.dispose()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session")
async def client(_ensure_test_db):
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
