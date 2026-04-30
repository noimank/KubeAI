import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.audit import AuditLogQueryParams


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(
        self,
        action: str,
        resource_type: str,
        ip_address: str,
        user_id: uuid.UUID | None = None,
        tenant_id: uuid.UUID | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def query_logs(
        self, query_params: AuditLogQueryParams, current_user: User
    ) -> tuple[list[tuple[AuditLog, str | None]], int]:
        query = select(AuditLog, User.username).outerjoin(User, AuditLog.user_id == User.id)

        if current_user.role == UserRole.ADMIN:
            if query_params.tenant_id is not None:
                query = query.where(AuditLog.tenant_id == query_params.tenant_id)
        elif current_user.role == UserRole.MLOPS:
            query = query.where(AuditLog.tenant_id == current_user.tenant_id)
        else:
            raise ForbiddenException("无权查看审计日志")

        if query_params.action:
            query = query.where(AuditLog.action.in_(query_params.action))
        if query_params.resource_type:
            query = query.where(AuditLog.resource_type.in_(query_params.resource_type))
        if query_params.username:
            query = query.where(User.username.ilike(f"%{query_params.username}%"))
        if query_params.user_id is not None:
            query = query.where(AuditLog.user_id == query_params.user_id)
        if query_params.start_time is not None:
            query = query.where(AuditLog.created_at >= query_params.start_time)
        if query_params.end_time is not None:
            query = query.where(AuditLog.created_at <= query_params.end_time)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = (
            query.order_by(AuditLog.created_at.desc())
            .offset((query_params.page - 1) * query_params.page_size)
            .limit(query_params.page_size)
        )
        result = await self.db.execute(query)
        rows = result.all()

        items = [(log, username) for log, username in rows]
        return items, total

    async def get_log(self, log_id: uuid.UUID, current_user: User) -> tuple[AuditLog, str | None]:
        result = await self.db.execute(
            select(AuditLog, User.username).outerjoin(User, AuditLog.user_id == User.id).where(AuditLog.id == log_id)
        )
        row = result.one_or_none()
        if not row:
            raise NotFoundException("审计日志不存在")

        log, username = row
        if current_user.role == UserRole.MLOPS and log.tenant_id != current_user.tenant_id:
            raise ForbiddenException("无权查看其他租户的审计日志")

        return log, username
