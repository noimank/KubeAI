"""SQL 查询执行 + Schema 浏览 + 结果保存 API。"""

import csv
import io
import json
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.security import decrypt_password
from app.models.db_connection import DbConnection
from app.schemas.base import BaseResponse
from app.schemas.db_connection import (
    ColumnInfo,
    QueryRequest,
    QueryResultResponse,
    SaveResultRequest,
    TableInfo,
)
from app.services.query_executor import QueryExecutor

DbDep = Annotated[AsyncSession, Depends(get_db)]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query-results", tags=["query-results"])


async def _get_connection(db: AsyncSession, tenant_id: uuid.UUID | None, connection_id: uuid.UUID) -> DbConnection:
    """获取连接并校验租户归属。"""
    if tenant_id is None:
        raise ForbiddenException("请先加入租户")
    result = await db.execute(
        select(DbConnection).where(DbConnection.id == connection_id, DbConnection.tenant_id == tenant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise NotFoundException("数据库连接不存在")
    return conn


@router.post("/execute", response_model=BaseResponse[QueryResultResponse])
async def execute_query(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "read"))],
    data: QueryRequest,
) -> BaseResponse[QueryResultResponse]:
    """执行 SQL 查询并返回结果。"""
    conn = await _get_connection(db, user.tenant_id, data.connection_id)
    password = decrypt_password(conn.encrypted_password)

    executor = QueryExecutor()
    try:
        result = await executor.execute_query(
            db_type=conn.db_type,
            host=conn.host,
            port=conn.port,
            database_name=conn.database_name,
            username=conn.username,
            password=password,
            sql=data.sql,
            max_rows=data.max_rows,
            timeout=data.timeout,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except TimeoutError:
        raise HTTPException(status_code=408, detail="查询超时，请简化查询或增加超时时间") from None

    return BaseResponse(data=QueryResultResponse(**result), message="查询成功")


@router.post("/save", response_model=BaseResponse[dict[str, Any]])
async def save_query_result(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "write"))],
    data: SaveResultRequest,
) -> BaseResponse[dict[str, Any]]:
    """将查询结果保存到平台文件系统。重新执行查询获取最新数据。"""
    import os

    if user.tenant_id is None:
        raise ForbiddenException("请先加入租户")

    from app.models.tenant import Tenant

    tenant_row = await db.get(Tenant, user.tenant_id)
    if tenant_row is None:
        raise NotFoundException("租户不存在")

    conn = await _get_connection(db, user.tenant_id, data.connection_id)
    password = decrypt_password(conn.encrypted_password)

    # 重新执行查询
    executor = QueryExecutor()
    try:
        result = await executor.execute_query(
            db_type=conn.db_type,
            host=conn.host,
            port=conn.port,
            database_name=conn.database_name,
            username=conn.username,
            password=password,
            sql=data.sql,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except TimeoutError:
        raise HTTPException(status_code=408, detail="查询超时，请简化查询或增加超时时间") from None

    # 验证目标路径安全性
    from app.integrations.storage.filesystem_browser import FilesystemBrowserSecurity

    fs_security = FilesystemBrowserSecurity(username=user.username, tenant_name=tenant_row.name)
    try:
        host_dir, _canonical = fs_security.resolve_container_path(data.target_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # 确保文件在目标路径内
    safe_filename = os.path.basename(data.filename) or "result.csv"
    file_path = host_dir / safe_filename

    # 写入文件
    import aiofiles

    if data.format == "json":
        content = json.dumps(
            [dict(zip(result["columns"], row, strict=False)) for row in result["rows"]],
            ensure_ascii=False,
            default=str,
        )
        async with aiofiles.open(str(file_path), "w", encoding="utf-8") as f:
            await f.write(content)
    else:
        # CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(result["columns"])
        for row in result["rows"]:
            writer.writerow(row)
        async with aiofiles.open(str(file_path), "w", encoding="utf-8", newline="") as f:
            await f.write(output.getvalue())

    return BaseResponse(
        data={"path": f"{data.target_path}/{safe_filename}", "rows": result["row_count"]},
        message="保存成功",
    )


@router.get("/tables/{connection_id}", response_model=BaseResponse[list[TableInfo]])
async def list_tables(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "read"))],
    connection_id: uuid.UUID,
) -> BaseResponse[list[TableInfo]]:
    """获取数据库表/视图列表。"""
    conn = await _get_connection(db, user.tenant_id, connection_id)
    password = decrypt_password(conn.encrypted_password)

    executor = QueryExecutor()
    try:
        tables, truncated = await executor.list_tables(
            db_type=conn.db_type,
            host=conn.host,
            port=conn.port,
            database_name=conn.database_name,
            username=conn.username,
            password=password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    message = "查询成功"
    if truncated:
        logger.info("租户 %s 连接 %s 表列表超出上限，仅返回前 %d 张", user.tenant_id, connection_id, len(tables))
        message = f"表数量超过单次上限，仅返回前 {len(tables)} 张"

    return BaseResponse(data=[TableInfo(**t) for t in tables], message=message)


@router.get(
    "/tables/{connection_id}/{table_name}/schema",
    response_model=BaseResponse[list[ColumnInfo]],
)
async def get_table_schema(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "read"))],
    connection_id: uuid.UUID,
    table_name: str,
    table_schema: str | None = Query(None, description="目标 schema（PostgreSQL 等）"),
) -> BaseResponse[list[ColumnInfo]]:
    """获取表列定义。"""
    conn = await _get_connection(db, user.tenant_id, connection_id)
    password = decrypt_password(conn.encrypted_password)

    executor = QueryExecutor()
    try:
        columns = await executor.get_table_schema(
            db_type=conn.db_type,
            host=conn.host,
            port=conn.port,
            database_name=conn.database_name,
            username=conn.username,
            password=password,
            table_name=table_name,
            table_schema=table_schema,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return BaseResponse(data=[ColumnInfo(**c) for c in columns], message="查询成功")
