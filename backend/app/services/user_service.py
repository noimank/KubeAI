import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import AuditAction, ResourceType, UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        username: str | None = None,
        email: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query = select(User).where(User.deleted_at.is_(None))

        if username:
            query = query.where(User.username.ilike(f"%{username}%"))
        if email:
            query = query.where(User.email.ilike(f"%{email}%"))
        if role:
            query = query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if start_time:
            query = query.where(User.created_at >= start_time)
        if end_time:
            query = query.where(User.created_at <= end_time)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        users = result.scalars().all()

        tenant_ids = {u.tenant_id for u in users if u.tenant_id}
        tenant_map: dict[uuid.UUID, str] = {}
        if tenant_ids:
            tenant_result = await self.db.execute(select(Tenant.id, Tenant.name).where(Tenant.id.in_(tenant_ids)))
            rows = tenant_result.all()
            tenant_map = {row[0]: row[1] for row in rows}

        items: list[dict[str, Any]] = []
        for user in users:
            items.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "auth_provider": user.auth_provider,
                    "tenant_id": user.tenant_id,
                    "tenant_name": tenant_map.get(user.tenant_id) if user.tenant_id else None,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                }
            )
        return items, total

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any]:
        result = await self.db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")

        tenant_name: str | None = None
        if user.tenant_id:
            tenant_result = await self.db.execute(select(Tenant.name).where(Tenant.id == user.tenant_id))
            row = tenant_result.one_or_none()
            if row:
                tenant_name = row[0]

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "auth_provider": user.auth_provider,
            "tenant_id": user.tenant_id,
            "tenant_name": tenant_name,
            "failed_login_attempts": user.failed_login_attempts,
            "locked_until": user.locked_until,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    async def update_user(
        self, user_id: uuid.UUID, data: dict[str, Any], audit_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        result = await self.db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")

        changes: dict[str, dict[str, Any]] = {}
        if "role" in data and data["role"] is not None:
            old_role = user.role
            user.role = data["role"]
            changes["role"] = {"old": old_role.value, "new": data["role"].value}
        if "tenant_id" in data:
            old_tenant_id = user.tenant_id
            user.tenant_id = data["tenant_id"]
            changes["tenant_id"] = {
                "old": str(old_tenant_id) if old_tenant_id else None,
                "new": str(data["tenant_id"]) if data["tenant_id"] else None,
            }

        await self.db.flush()
        await self.db.refresh(user)

        if audit_context and changes:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.USER,
                resource_id=str(user.id),
                detail=changes,
                **audit_context,
            )

        return await self.get_user(user_id)

    async def toggle_user_status(
        self, user_id: uuid.UUID, is_active: bool, audit_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        result = await self.db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")

        if user.is_active == is_active:
            raise ConflictException(f"用户已处于{'启用' if is_active else '禁用'}状态")

        user.is_active = is_active
        if is_active:
            user.failed_login_attempts = 0
            user.locked_until = None

        await self.db.flush()
        await self.db.refresh(user)

        if audit_context:
            audit_svc = AuditService(self.db)
            action = AuditAction.ENABLE if is_active else AuditAction.DISABLE
            await audit_svc.log_action(
                action=action,
                resource_type=ResourceType.USER,
                resource_id=str(user.id),
                detail={"is_active": is_active},
                **audit_context,
            )

        return await self.get_user(user_id)

    async def delete_user(self, user_id: uuid.UUID, audit_context: dict[str, Any] | None = None) -> None:
        result = await self.db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")

        user.deleted_at = datetime.now(UTC)
        user.is_active = False
        await self.db.flush()

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.DELETE,
                resource_type=ResourceType.USER,
                resource_id=str(user.id),
                detail={"username": user.username, "email": user.email},
                **audit_context,
            )
