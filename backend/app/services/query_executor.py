"""SQL 查询执行引擎 + Schema 浏览。

每个请求动态创建 SQLAlchemy engine，用完即弃，避免维护持久连接池。
支持 PostgreSQL (asyncpg)、MySQL (aiomysql) 原生异步，Spark/Hive (pyhive)、MSSQL (pymssql) 通过 asyncio.to_thread 包装。
"""

import asyncio
import re
import time
from typing import Any

from sqlalchemy import create_engine, text

from app.core.config import settings

# 只读 SQL 关键字白名单
_READONLY_KEYWORDS = {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"}

# 表名/Schema 名安全字符集: 拒绝引号、分号、注释、空白等 SQL 注入载体
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$.\-]{1,255}$")


def _validate_identifier(name: str) -> str:
    """校验表名/Schema 名只含安全标识符字符, 防止拼接 SQL 时注入。"""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"非法表名或 Schema 名: {name!r}")
    return name


# SHOW 子命令白名单：只允许读取元数据/表结构的 SHOW 变体
_ALLOWED_SHOW_COMMANDS = frozenset(
    {
        # MySQL / Doris: 元数据与表结构
        "TABLES",
        "COLUMNS",
        "FULL COLUMNS",
        "FIELDS",
        "FULL FIELDS",
        "DATABASES",
        "SCHEMAS",
        "CREATE TABLE",
        "CREATE VIEW",
        "INDEX",
        "INDEXES",
        "KEYS",
        "TABLE STATUS",
        "COLUMN STATISTICS",
        "VARIABLES",
        "STATUS",
        "WARNINGS",
        "ERRORS",
        "CHARSET",
        "CHARACTER SET",
        "COLLATION",
        "ENGINES",
        "PLUGINS",
        "PROCEDURE STATUS",
        "FUNCTION STATUS",
        "TRIGGERS",
        "EVENTS",
        # Spark / Hive: 分区、表属性、函数、视图
        "PARTITIONS",
        "TBLPROPERTIES",
        "FUNCTIONS",
        "VIEWS",
    }
)

# Dialect 映射
ASYNC_DIALECTS = {
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
    "doris": "mysql+aiomysql",
}
SYNC_DIALECTS = {
    "spark": "hive+pyhive",
    "hive": "hive+pyhive",
    "mssql": "mssql+pymssql",
}


def _sanitize_sql(sql: str) -> str:
    """校验 SQL 安全性：仅允许只读语句，拒绝多语句。"""
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise ValueError("不允许执行多语句查询")

    tokens = stripped.split(maxsplit=2)
    first_keyword = tokens[0].upper() if tokens else ""
    if first_keyword not in _READONLY_KEYWORDS:
        raise ValueError(f"仅允许只读查询（SELECT/SHOW/DESCRIBE/EXPLAIN），收到: {first_keyword}")

    # SHOW 需要额外校验子命令
    if first_keyword == "SHOW":
        remaining = " ".join(tokens[1:]).upper().lstrip()
        # 匹配白名单中的 SHOW 子命令前缀
        allowed = False
        for cmd in sorted(_ALLOWED_SHOW_COMMANDS, key=len, reverse=True):
            if remaining.startswith(cmd):
                allowed = True
                break
        if not allowed:
            raise ValueError(f"不允许的 SHOW 子命令: SHOW {remaining.split()[0] if remaining else ''}")

    return stripped


def _build_connection_url(
    db_type: str,
    host: str,
    port: int,
    database_name: str,
    username: str,
    password: str,
    extra_params: str | None = None,
) -> str:
    """构建 SQLAlchemy 连接 URL。"""
    import urllib.parse

    encoded_password = urllib.parse.quote_plus(password)
    encoded_user = urllib.parse.quote_plus(username)

    if db_type in ASYNC_DIALECTS:
        dialect = ASYNC_DIALECTS[db_type]
        url = f"{dialect}://{encoded_user}:{encoded_password}@{host}:{port}/{database_name}"
    elif db_type in SYNC_DIALECTS:
        dialect = SYNC_DIALECTS[db_type]
        url = f"{dialect}://{encoded_user}:{encoded_password}@{host}:{port}/{database_name}"
    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")

    if extra_params:
        try:
            import json

            params = json.loads(extra_params)
            if params:
                from urllib.parse import urlencode

                url += "?" + urlencode(params)
        except json.JSONDecodeError:
            pass

    return url


class QueryExecutor:
    """无状态 SQL 执行器。"""

    async def execute_query(
        self,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str,
        sql: str,
        max_rows: int | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """执行 SQL 查询并返回结构化结果。"""
        max_rows = max_rows or settings.DATA_EXPLORE_MAX_ROWS
        timeout = timeout or settings.DATA_EXPLORE_QUERY_TIMEOUT

        sanitized = _sanitize_sql(sql)

        # 自动追加 LIMIT（仅对无 LIMIT 的 SELECT）
        upper = sanitized.upper()
        if upper.startswith("SELECT") and "LIMIT" not in upper:
            sanitized = f"SELECT * FROM ({sanitized}) AS _dq LIMIT {max_rows}"

        url = _build_connection_url(db_type, host, port, database_name, username, password)

        if db_type in ASYNC_DIALECTS:
            return await self._execute_async(db_type, url, sanitized, max_rows, timeout)
        else:
            return await asyncio.wait_for(
                asyncio.to_thread(self._execute_sync, db_type, url, sanitized, max_rows, timeout),
                timeout=timeout + 5,
            )

    async def _execute_async(self, db_type: str, url: str, sql: str, max_rows: int, timeout: int) -> dict[str, Any]:
        """异步驱动执行（PostgreSQL/MySQL）。"""
        from sqlalchemy.ext.asyncio import create_async_engine

        # PG 服务端强制只读事务: 阻断 WITH ... DELETE/UPDATE 数据修改 CTE 绕过只读白名单
        connect_args = {"server_settings": {"default_transaction_read_only": "on"}} if db_type == "postgresql" else {}
        engine = create_async_engine(url, pool_size=1, pool_pre_ping=True, connect_args=connect_args)
        try:
            start = time.monotonic()
            async with engine.connect() as conn:
                result = await asyncio.wait_for(conn.execute(text(sql)), timeout=timeout)
                columns = list(result.keys())
                rows = [list(row) for row in result.fetchall()]
            elapsed = (time.monotonic() - start) * 1000

            truncated = len(rows) >= max_rows
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
                "execution_time_ms": round(elapsed, 2),
            }
        finally:
            await engine.dispose()

    def _execute_sync(self, db_type: str, url: str, sql: str, max_rows: int, timeout: int) -> dict[str, Any]:
        """同步驱动执行（Spark/Hive/MSSQL），在 asyncio.to_thread 中运行。超时由外层 asyncio.wait_for 控制。"""
        engine = create_engine(url, pool_size=1, pool_pre_ping=True)
        try:
            start = time.monotonic()
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = [list(row) for row in result.fetchall()]
            elapsed = (time.monotonic() - start) * 1000

            truncated = len(rows) >= max_rows
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
                "execution_time_ms": round(elapsed, 2),
            }
        finally:
            engine.dispose()

    async def list_tables(
        self,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str,
    ) -> list[dict[str, Any]]:
        """列出数据库中的表和视图。"""
        if db_type == "postgresql":
            sql = """
                SELECT table_name, table_schema,
                       CASE table_type WHEN 'VIEW' THEN 'view' ELSE 'table' END AS table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
            """
        elif db_type in ("mysql", "doris"):
            sql = (
                "SELECT TABLE_NAME AS table_name, TABLE_SCHEMA AS table_schema, "
                "CASE TABLE_TYPE WHEN 'VIEW' THEN 'view' ELSE 'table' END AS table_type "
                "FROM information_schema.tables WHERE TABLE_SCHEMA = DATABASE() "
                "ORDER BY TABLE_NAME"
            )
        elif db_type in ("spark", "hive"):
            sql = "SHOW TABLES"
        elif db_type == "mssql":
            sql = (
                "SELECT TABLE_NAME AS table_name, TABLE_SCHEMA AS table_schema, "
                "CASE TABLE_TYPE WHEN 'VIEW' THEN 'view' ELSE 'table' END AS table_type "
                "FROM information_schema.tables "
                "WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW') ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

        result = await self.execute_query(db_type, host, port, database_name, username, password, sql, max_rows=5000)

        tables = []
        for row in result["rows"]:
            if db_type in ("spark", "hive"):
                # SHOW TABLES 返回格式因 Spark 版本而异:
                #   2 列: [tableName, isTemporary]
                #   3 列: [namespace, tableName, isTemporary]
                col_count = len(row)
                if col_count >= 3:
                    name, is_temp = row[1], row[2]
                elif col_count == 2:
                    name, is_temp = row[0], row[1]
                else:
                    name, is_temp = row[0], False
                # 跳过临时表（Spark 自动生成的 CTE / TEMP VIEW 等）
                if is_temp:
                    continue
                tables.append({"name": name, "table_schema": None, "type": "table"})
            else:
                tables.append(
                    {
                        "name": row[0] if len(row) > 0 else "",
                        "table_schema": row[1] if len(row) > 1 else None,
                        "type": row[2] if len(row) > 2 else "table",
                    }
                )
        return tables

    async def get_table_schema(
        self,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str,
        table_name: str,
        table_schema: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取表的列定义。"""
        _validate_identifier(table_name)
        if table_schema:
            _validate_identifier(table_schema)
        if db_type == "postgresql":
            if table_schema:
                schema_filter = f"AND c.table_schema = '{table_schema}'"
                pk_schema_filter = f"AND tc.table_schema = '{table_schema}'"
            else:
                schema_filter = "AND c.table_schema NOT IN ('pg_catalog', 'information_schema')"
                pk_schema_filter = ""
            sql = f"""
                SELECT c.column_name, c.data_type, c.is_nullable,
                       c.column_default,
                       CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END,
                       pg_catalog.col_description(
                           format('%I.%I', c.table_schema, c.table_name)::regclass,
                           c.ordinal_position
                       )
                FROM information_schema.columns c
                LEFT JOIN (
                    SELECT ku.column_name, ku.table_schema
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage ku
                      ON tc.constraint_name = ku.constraint_name
                     AND tc.table_schema = ku.table_schema
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND tc.table_name = '{table_name}'
                      {pk_schema_filter}
                ) pk ON c.column_name = pk.column_name AND c.table_schema = pk.table_schema
                WHERE c.table_name = '{table_name}'
                  {schema_filter}
                ORDER BY c.table_schema, c.ordinal_position
            """
        elif db_type in ("mysql", "doris"):
            sql = f"SHOW COLUMNS FROM `{table_name}`"
        elif db_type in ("spark", "hive"):
            sql = f"DESCRIBE {table_name}"
        elif db_type == "mssql":
            if table_schema:
                schema_filter = f"AND c.TABLE_SCHEMA = '{table_schema}'"
                pk_schema_filter = f"AND tc.TABLE_SCHEMA = '{table_schema}'"
            else:
                schema_filter = ""
                pk_schema_filter = ""
            sql = f"""
                SELECT c.COLUMN_NAME, c.DATA_TYPE,
                       CASE c.IS_NULLABLE WHEN 'YES' THEN 'YES' ELSE 'NO' END,
                       c.COLUMN_DEFAULT,
                       CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END,
                       NULL
                FROM information_schema.COLUMNS c
                LEFT JOIN (
                    SELECT ku.COLUMN_NAME
                    FROM information_schema.TABLE_CONSTRAINTS tc
                    JOIN information_schema.KEY_COLUMN_USAGE ku
                      ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
                    WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                      AND tc.TABLE_NAME = '{table_name}'
                      {pk_schema_filter}
                ) pk ON c.COLUMN_NAME = pk.COLUMN_NAME
                WHERE c.TABLE_NAME = '{table_name}'
                  {schema_filter}
                ORDER BY c.ORDINAL_POSITION
            """
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

        result = await self.execute_query(db_type, host, port, database_name, username, password, sql, max_rows=500)

        columns = []
        for row in result["rows"]:
            if db_type == "postgresql":
                columns.append(
                    {
                        "name": row[0],
                        "data_type": row[1],
                        "nullable": row[2] == "YES",
                        "default_value": row[3],
                        "is_primary_key": row[4],
                        "comment": row[5],
                    }
                )
            elif db_type in ("mysql", "doris"):
                # SHOW COLUMNS: Field, Type, Null, Key, Default, Extra
                columns.append(
                    {
                        "name": row[0],
                        "data_type": row[1],
                        "nullable": row[2] == "YES",
                        "is_primary_key": row[3] == "PRI",
                        "default_value": row[4],
                        "comment": None,
                    }
                )
            elif db_type in ("spark", "hive"):
                # DESCRIBE: col_name, data_type, comment
                name = row[0].strip() if row[0] else ""
                if name and not name.startswith("#"):
                    columns.append(
                        {
                            "name": name,
                            "data_type": row[1] if len(row) > 1 else "",
                            "nullable": True,
                            "is_primary_key": False,
                            "default_value": None,
                            "comment": row[2] if len(row) > 2 else None,
                        }
                    )
            elif db_type == "mssql":
                columns.append(
                    {
                        "name": row[0],
                        "data_type": row[1],
                        "nullable": row[2] == "YES",
                        "default_value": row[3],
                        "is_primary_key": bool(row[4]),
                        "comment": row[5],
                    }
                )
        return columns
