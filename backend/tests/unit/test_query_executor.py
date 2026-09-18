"""query_executor 安全防护与连接引擎缓存单元测试.

覆盖维度:
  * _validate_identifier: 注入载荷(引号/分号/注释/空白)拒绝, 常规标识符放行
  * get_table_schema: 非法表名在构建 SQL 前即拒绝 (不触达数据库)
  * _execute_async: PostgreSQL 连接携带只读服务端设置与建连超时, MySQL 携带 connect_timeout
  * 引擎缓存: 同连接目标复用引擎, 密码变更即隔离, 查询超时后废弃缓存引擎
  * list_tables: PG 走 pg_catalog 直查, 截断标志透传
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import query_executor
from app.services.query_executor import QueryExecutor, _validate_identifier


@pytest.fixture(autouse=True)
def _clear_engine_cache():
    """隔离引擎缓存, 避免测试间复用 mock 引擎。"""
    query_executor._async_engines.clear()
    yield
    query_executor._async_engines.clear()


class TestValidateIdentifier:
    @pytest.mark.parametrize("ok", ["users", "t_1", "MyTable", "schema.table", "col-name", "a$b", "T" * 255])
    def test_allows_safe_identifiers(self, ok):
        assert _validate_identifier(ok) == ok

    @pytest.mark.parametrize(
        "bad",
        [
            "x'; DROP TABLE t; --",
            'x"; SELECT 1',
            "x` DELETE FROM t",
            "a b",
            "a;b",
            "/* comment */",
            "",
            "x;--",
            "\\x",
        ],
    )
    def test_rejects_injection_payloads(self, bad):
        with pytest.raises(ValueError, match="非法表名"):
            _validate_identifier(bad)


class TestGetTableSchemaValidation:
    async def test_malicious_table_name_rejected_before_query(self):
        executor = QueryExecutor()
        with (
            patch.object(executor, "execute_query", new_callable=AsyncMock) as mock_exec,
            pytest.raises(ValueError, match="非法表名"),
        ):
            await executor.get_table_schema(
                db_type="postgresql",
                host="h",
                port=5432,
                database_name="db",
                username="u",
                password="p",
                table_name="x' AND 1=1 --",
            )
        mock_exec.assert_not_awaited()

    async def test_malicious_schema_rejected(self):
        executor = QueryExecutor()
        with pytest.raises(ValueError, match="非法表名"):
            await executor.get_table_schema(
                db_type="postgresql",
                host="h",
                port=5432,
                database_name="db",
                username="u",
                password="p",
                table_name="users",
                table_schema="pg_catalog'; SELECT 1 --",
            )


def _mock_async_engine(create_engine_mock):
    """构造可 ``async with engine.connect()`` 的 mock, 返回 (engine, conn)."""
    engine = create_engine_mock.return_value
    engine.dispose = AsyncMock()
    conn = AsyncMock()
    execute_result = MagicMock()
    execute_result.keys.return_value = []
    execute_result.fetchall.return_value = []
    conn.execute = AsyncMock(return_value=execute_result)
    engine.connect.return_value.__aenter__.return_value = conn
    return engine, conn


class TestPostgresReadOnlyConnection:
    async def test_postgres_engine_gets_readonly_and_connect_timeout(self):
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine_mock:
            _mock_async_engine(create_engine_mock)
            await QueryExecutor()._execute_async("postgresql", "postgresql+asyncpg://u:p@h/db", "SELECT 1", 10, 5)

        _, kwargs = create_engine_mock.call_args
        assert kwargs["connect_args"] == {
            "server_settings": {"default_transaction_read_only": "on"},
            "timeout": query_executor._ENGINE_CONNECT_TIMEOUT,
        }

    async def test_mysql_engine_gets_connect_timeout(self):
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine_mock:
            _mock_async_engine(create_engine_mock)
            await QueryExecutor()._execute_async("mysql", "mysql+aiomysql://u:p@h/db", "SELECT 1", 10, 5)

        _, kwargs = create_engine_mock.call_args
        assert kwargs["connect_args"] == {"connect_timeout": query_executor._ENGINE_CONNECT_TIMEOUT}


class TestEngineCache:
    async def test_same_url_reuses_engine(self):
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine_mock:
            _mock_async_engine(create_engine_mock)
            executor = QueryExecutor()
            url = "postgresql+asyncpg://u:p@h/db"
            await executor._execute_async("postgresql", url, "SELECT 1", 10, 5)
            await executor._execute_async("postgresql", url, "SELECT 2", 10, 5)

        assert create_engine_mock.call_count == 1
        assert len(query_executor._async_engines) == 1

    async def test_password_change_creates_isolated_engine(self):
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine_mock:
            _mock_async_engine(create_engine_mock)
            executor = QueryExecutor()
            await executor._execute_async("postgresql", "postgresql+asyncpg://u:p_old@h/db", "SELECT 1", 10, 5)
            await executor._execute_async("postgresql", "postgresql+asyncpg://u:p_new@h/db", "SELECT 1", 10, 5)

        assert create_engine_mock.call_count == 2
        assert len(query_executor._async_engines) == 2

    async def test_timeout_disposes_and_evicts_engine(self):
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine_mock:
            engine, conn = _mock_async_engine(create_engine_mock)
            conn.execute = AsyncMock(side_effect=asyncio.TimeoutError)
            executor = QueryExecutor()
            url = "postgresql+asyncpg://u:p@h/db"
            with pytest.raises(TimeoutError):
                await executor._execute_async("postgresql", url, "SELECT pg_sleep(100)", 10, 5)

        engine.dispose.assert_awaited()
        assert len(query_executor._async_engines) == 0

    async def test_close_cached_engines_disposes_all(self):
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine_mock:
            engine, _ = _mock_async_engine(create_engine_mock)
            executor = QueryExecutor()
            await executor._execute_async("postgresql", "postgresql+asyncpg://u:p@h/db", "SELECT 1", 10, 5)
            await query_executor.close_cached_engines()

        engine.dispose.assert_awaited()
        assert len(query_executor._async_engines) == 0


class TestListTables:
    async def test_postgres_uses_pg_catalog_and_returns_truncation(self):
        executor = QueryExecutor()
        with patch.object(executor, "execute_query", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "columns": ["table_name", "table_schema", "table_type"],
                "rows": [["users", "public", "table"]],
                "row_count": 1,
                "truncated": False,
                "execution_time_ms": 1,
            }
            tables, truncated = await executor.list_tables(
                db_type="postgresql", host="h", port=5432, database_name="db", username="u", password="p"
            )

        sql = mock_exec.call_args.args[6]
        assert "pg_catalog.pg_class" in sql
        assert "information_schema" not in sql.replace("'pg_catalog', 'information_schema'", "")
        assert tables == [{"name": "users", "table_schema": "public", "type": "table"}]
        assert truncated is False

    async def test_truncation_flag_propagates(self):
        executor = QueryExecutor()
        with patch.object(executor, "execute_query", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "columns": ["table_name", "table_schema", "table_type"],
                "rows": [],
                "row_count": 0,
                "truncated": True,
                "execution_time_ms": 1,
            }
            _, truncated = await executor.list_tables(
                db_type="postgresql", host="h", port=5432, database_name="db", username="u", password="p"
            )

        assert truncated is True
        assert mock_exec.call_args.kwargs["max_rows"] == QueryExecutor.TABLE_LIST_LIMIT
