"""数据库连接 Pydantic Schema。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DbConnectionCreate(BaseModel):
    """创建数据库连接请求。"""

    name: str = Field(..., min_length=1, max_length=200, description="连接名称")
    db_type: str = Field(..., description="数据库类型: postgresql/mysql/spark/hive/mssql/doris")
    host: str = Field(..., min_length=1, max_length=500, description="主机地址")
    port: int = Field(..., gt=0, lt=65536, description="端口")
    database_name: str = Field(..., min_length=1, max_length=200, description="数据库名")
    username: str = Field(..., min_length=1, max_length=200, description="用户名")
    password: str = Field(..., min_length=1, description="密码（明文传入，加密存储）")
    extra_params: str | None = Field(None, description="额外连接参数 JSON 字符串")
    description: str | None = Field(None, max_length=500, description="备注")


class DbConnectionUpdate(BaseModel):
    """更新数据库连接请求，所有字段可选。password=None 表示不修改密码。"""

    name: str | None = Field(None, min_length=1, max_length=200, description="连接名称")
    db_type: str | None = Field(None, description="数据库类型")
    host: str | None = Field(None, min_length=1, max_length=500, description="主机地址")
    port: int | None = Field(None, gt=0, lt=65536, description="端口")
    database_name: str | None = Field(None, min_length=1, max_length=200, description="数据库名")
    username: str | None = Field(None, min_length=1, max_length=200, description="用户名")
    password: str | None = Field(None, min_length=1, description="密码（留空表示不修改）")
    extra_params: str | None = Field(None, description="额外连接参数 JSON 字符串")
    description: str | None = Field(None, max_length=500, description="备注")


class DbConnectionResponse(BaseModel):
    """数据库连接响应（不含密码）。"""

    id: uuid.UUID
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    extra_params: str | None = None
    description: str | None = None
    created_by: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QueryRequest(BaseModel):
    """SQL 查询请求。"""

    connection_id: uuid.UUID = Field(..., description="数据库连接 ID")
    sql: str = Field(..., min_length=1, description="SQL 查询语句")
    max_rows: int = Field(1000, ge=1, le=10000, description="最大返回行数")
    timeout: int = Field(30, ge=1, le=300, description="查询超时（秒）")


class QueryResultResponse(BaseModel):
    """SQL 查询结果响应。"""

    columns: list[str] = Field(default_factory=list, description="列名列表")
    rows: list[list[Any]] = Field(default_factory=list, description="数据行列表")
    row_count: int = Field(0, description="实际返回行数")
    truncated: bool = Field(False, description="结果是否被截断")
    execution_time_ms: float = Field(0, description="执行耗时（毫秒）")


class SaveResultRequest(BaseModel):
    """保存查询结果到文件系统请求。"""

    connection_id: uuid.UUID = Field(..., description="数据库连接 ID")
    sql: str = Field(..., min_length=1, description="SQL 查询语句")
    target_path: str = Field(..., min_length=1, description="目标目录（容器路径）")
    filename: str = Field(..., min_length=1, description="文件名（如 result.csv）")
    format: str = Field("csv", description="输出格式: csv / json")


class TableInfo(BaseModel):
    """数据库表信息。"""

    name: str = Field(..., description="表名")
    table_schema: str | None = Field(None, description="所属 schema")
    type: str = Field("table", description="table 或 view")


class ColumnInfo(BaseModel):
    """数据库列信息。"""

    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    default_value: str | None = None
    comment: str | None = None
