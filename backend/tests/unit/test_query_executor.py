"""query_executor 安全防护单元测试 — 标识符校验与 PG 只读连接.

覆盖维度:
  * _validate_identifier: 注入载荷(引号/分号/注释/空白)拒绝, 常规标识符放行
  * get_table_schema: 非法表名在构建 SQL 前即拒绝 (不触达数据库)
  * _execute_async: PostgreSQL 连接携带 default_transaction_read_only 服务端只读设置
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.query_executor import QueryExecutor, _validate_identifier


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
    async def test_postgres_engine_gets_readonly_server_setting(self):
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine_mock:
            _mock_async_engine(create_engine_mock)
            await QueryExecutor()._execute_async("postgresql", "postgresql+asyncpg://u:p@h/db", "SELECT 1", 10, 5)

        _, kwargs = create_engine_mock.call_args
        assert kwargs["connect_args"] == {"server_settings": {"default_transaction_read_only": "on"}}

    async def test_mysql_engine_has_no_server_settings(self):
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as create_engine_mock:
            _mock_async_engine(create_engine_mock)
            await QueryExecutor()._execute_async("mysql", "mysql+aiomysql://u:p@h/db", "SELECT 1", 10, 5)

        _, kwargs = create_engine_mock.call_args
        assert kwargs["connect_args"] == {}
