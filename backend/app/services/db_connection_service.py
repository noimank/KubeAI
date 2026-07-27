"""数据库连接管理服务：CRUD + 密码加解密 + 连接测试。"""

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import decrypt_password, encrypt_password
from app.models.db_connection import DbConnection
from app.schemas.db_connection import DbConnectionCreate, DbConnectionUpdate


class DbConnectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, tenant_id: uuid.UUID, user_id: uuid.UUID, data: DbConnectionCreate) -> dict[str, Any]:
        """创建数据库连接，密码加密存储。"""
        # 检查租户内名称唯一
        existing = await self.db.execute(
            select(DbConnection).where(DbConnection.tenant_id == tenant_id, DbConnection.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise ConflictException("连接名称已存在")

        conn = DbConnection(
            tenant_id=tenant_id,
            created_by=user_id,
            name=data.name,
            db_type=data.db_type,
            host=data.host,
            port=data.port,
            database_name=data.database_name,
            username=data.username,
            encrypted_password=encrypt_password(data.password),
            extra_params=data.extra_params,
            description=data.description,
        )
        self.db.add(conn)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException("连接名称已存在") from exc

        await self.db.refresh(conn)
        return self._to_dict(conn)

    async def list_connections(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页列出租户的连接配置。"""
        base = select(DbConnection).where(DbConnection.tenant_id == tenant_id)
        count_base = select(func.count()).select_from(DbConnection).where(DbConnection.tenant_id == tenant_id)

        if search:
            like = f"%{search}%"
            base = base.where(DbConnection.name.ilike(like) | DbConnection.host.ilike(like))
            count_base = count_base.where(DbConnection.name.ilike(like) | DbConnection.host.ilike(like))

        # Total count
        total_result = await self.db.execute(count_base)
        total = total_result.scalar() or 0

        # Paginated rows
        offset = (page - 1) * page_size
        result = await self.db.execute(base.order_by(DbConnection.updated_at.desc()).offset(offset).limit(page_size))
        items = [self._to_dict(row) for row in result.scalars().all()]

        return items, total

    async def get(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> dict[str, Any]:
        """获取单个连接（不含密码）。"""
        conn = await self._get_or_404(tenant_id, connection_id)
        return self._to_dict(conn)

    async def update(self, tenant_id: uuid.UUID, connection_id: uuid.UUID, data: DbConnectionUpdate) -> dict[str, Any]:
        """更新连接配置。password=None 时保留原密码。"""
        conn = await self._get_or_404(tenant_id, connection_id)

        update_data = data.model_dump(exclude_unset=True)

        # 名称唯一性检查
        if "name" in update_data and update_data["name"] != conn.name:
            existing = await self.db.execute(
                select(DbConnection).where(
                    DbConnection.tenant_id == tenant_id,
                    DbConnection.name == update_data["name"],
                    DbConnection.id != connection_id,
                )
            )
            if existing.scalar_one_or_none():
                raise ConflictException("连接名称已存在")

        # 密码加密
        if "password" in update_data and update_data["password"] is not None:
            update_data["encrypted_password"] = encrypt_password(update_data.pop("password"))

        stmt = (
            update(DbConnection)
            .where(DbConnection.id == connection_id, DbConnection.tenant_id == tenant_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)
        await self.db.flush()
        await self.db.refresh(conn)
        return self._to_dict(conn)

    async def delete(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> None:
        """删除连接配置。"""
        conn = await self._get_or_404(tenant_id, connection_id)
        await self.db.delete(conn)
        await self.db.flush()

    async def test_connection(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> dict[str, Any]:
        """测试连接连通性：建立连接 + 执行 SELECT 1。"""
        conn = await self._get_or_404(tenant_id, connection_id)
        password = decrypt_password(conn.encrypted_password)

        from app.services.query_executor import QueryExecutor

        executor = QueryExecutor()
        start = __import__("time").monotonic()
        try:
            await executor.execute_query(
                db_type=conn.db_type,
                host=conn.host,
                port=conn.port,
                database_name=conn.database_name,
                username=conn.username,
                password=password,
                sql="SELECT 1",
                max_rows=1,
                timeout=10,
            )
            elapsed_ms = (__import__("time").monotonic() - start) * 1000
            return {"success": True, "message": f"连接成功（{elapsed_ms:.0f}ms）"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {e}"}

    async def _get_or_404(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> DbConnection:
        result = await self.db.execute(
            select(DbConnection).where(DbConnection.id == connection_id, DbConnection.tenant_id == tenant_id)
        )
        conn = result.scalar_one_or_none()
        if not conn:
            raise NotFoundException("数据库连接不存在")
        return conn

    @staticmethod
    def _to_dict(conn: DbConnection) -> dict[str, Any]:
        return {
            "id": conn.id,
            "name": conn.name,
            "db_type": conn.db_type,
            "host": conn.host,
            "port": conn.port,
            "database_name": conn.database_name,
            "username": conn.username,
            "extra_params": conn.extra_params,
            "description": conn.description,
            "created_by": conn.created_by,
            "tenant_id": conn.tenant_id,
            "created_at": conn.created_at,
            "updated_at": conn.updated_at,
        }
