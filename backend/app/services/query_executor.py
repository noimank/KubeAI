"""SQL 查询执行引擎 + Schema 浏览。

异步驱动（PostgreSQL/MySQL/Doris）的 SQLAlchemy engine 按连接目标缓存复用，避免每次
请求重复 TCP/认证握手；闲置超 TTL 自动回收，进程退出时统一 dispose。同步驱动
（Spark/Hive/MSSQL）连接生命周期绑定单请求线程，不缓存，仍通过 asyncio.to_thread 包装。
"""

import asyncio
import hashlib
import logging
import re
import time
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings

logger = logging.getLogger(__name__)

# 引擎闲置回收秒数：超过后在下一次请求时 dispose，避免向用户数据库长期持有空闲连接
_ENGINE_IDLE_TTL_SECONDS = 300
# 建连超时（秒）：驱动默认普遍偏长（asyncpg 60s），防火墙丢包时前端会长时间转圈
_ENGINE_CONNECT_TIMEOUT = 10

# 异步引擎缓存: cache_key -> (engine, 最后使用时刻 monotonic)
_async_engines: dict[str, tuple[AsyncEngine, float]] = {}


def _engine_cache_key(url: str) -> str:
    """连接目标缓存键。URL 含账号密码，缓存里只保留其摘要。"""
    return hashlib.sha256(url.encode()).hexdigest()


def _connect_args(db_type: str) -> dict[str, Any]:
    """驱动级建连参数：PG 只读事务 + 各驱动受控建连超时。"""
    if db_type == "postgresql":
        # PG 服务端强制只读事务: 阻断 WITH ... DELETE/UPDATE 数据修改 CTE 绕过只读白名单
        return {
            "server_settings": {"default_transaction_read_only": "on"},
            "timeout": _ENGINE_CONNECT_TIMEOUT,
        }
    if db_type in ("mysql", "doris"):
        return {"connect_timeout": _ENGINE_CONNECT_TIMEOUT}
    return {}


async def _dispose_engine(engine: "AsyncEngine") -> None:
    try:
        await engine.dispose()
    except Exception:
        logger.warning("数据探索引擎回收失败", exc_info=True)


async def _get_cached_engine(db_type: str, url: str) -> "AsyncEngine":
    """取缓存引擎并触活；不存在则创建。池化连接让首个请求建连、后续请求直接复用。"""
    cache_key = _engine_cache_key(url)
    now = time.monotonic()

    stale = [k for k, (_, ts) in _async_engines.items() if now - ts > _ENGINE_IDLE_TTL_SECONDS]
    for key in stale:
        engine, _ = _async_engines.pop(key)
        await _dispose_engine(engine)

    entry = _async_engines.get(cache_key)
    if entry is None:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(
            url,
            pool_size=2,
            max_overflow=3,
            pool_pre_ping=True,
            connect_args=_connect_args(db_type),
        )
        _async_engines[cache_key] = (engine, now)
        return engine

    _async_engines[cache_key] = (entry[0], now)
    return entry[0]


async def close_cached_engines() -> None:
    """进程退出时回收全部缓存引擎（FastAPI lifespan shutdown 调用）。"""
    engines = [entry[0] for entry in _async_engines.values()]
    _async_engines.clear()
    for engine in engines:
        await _dispose_engine(engine)


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
        """异步驱动执行（PostgreSQL/MySQL/Doris），引擎缓存复用；建连+执行+取数统一受 timeout 约束。"""
        engine = await _get_cached_engine(db_type, url)

        async def _run() -> tuple[list[str], list[list[Any]]]:
            async with engine.connect() as conn:
                result = await conn.execute(text(sql))
                columns = list(result.keys())
                rows = [list(row) for row in result.fetchall()]
                return columns, rows

        start = time.monotonic()
        try:
            columns, rows = await asyncio.wait_for(_run(), timeout=timeout)
        except TimeoutError:
            # 超时中断后连接可能停留在未完成的协议状态，直接废弃该引擎的全部池化连接
            _async_engines.pop(_engine_cache_key(url), None)
            await _dispose_engine(engine)
            raise
        elapsed = (time.monotonic() - start) * 1000

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(rows) >= max_rows,
            "execution_time_ms": round(elapsed, 2),
        }

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

    # 表列表单次上限：超出即截断并向上游返回截断标志（前端有虚拟列表，可承载大库）
    TABLE_LIST_LIMIT = 20000

    async def list_tables(
        self,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str,
    ) -> tuple[list[dict[str, Any]], bool]:
        """列出数据库中的表和视图，返回 (表列表, 是否被上限截断)。"""
        if db_type == "postgresql":
            # pg_catalog 直查而非 information_schema：后者是带逐表权限检查的重视图，
            # 多 schema/多表库上慢一个量级
            sql = """
                SELECT c.relname AS table_name, n.nspname AS table_schema,
                       CASE WHEN c.relkind IN ('v', 'm') THEN 'view' ELSE 'table' END AS table_type
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                  AND n.nspname !~ '^pg_(toast|temp)'
                ORDER BY n.nspname, c.relname
            """
        elif db_type in ("mysql", "doris"):
            # MySQL 8 若实例设 information_schema_stats_expiry=0，此查询会逐表现算统计，
            # 大库显著变慢，由实例侧参数控制
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

        result = await self.execute_query(
            db_type, host, port, database_name, username, password, sql, max_rows=self.TABLE_LIST_LIMIT
        )
        if result["truncated"]:
            logger.warning(
                "数据探索表列表超出 %d 张上限，已截断: %s:%d/%s", self.TABLE_LIST_LIMIT, host, port, database_name
            )

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
        return tables, result["truncated"]

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
