import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.models.enums import AuditAction, ResourceType
from app.schemas.audit import AuditLogQueryParams, AuditLogResponse
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])

_query_none = Query(None)
_query_page = Query(1, ge=1)
_query_page_size = Query(20, ge=1, le=100)


@router.get("", response_model=PageResponse[AuditLogResponse])
async def list_audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("audit_logs", "read"))],
    action: list[AuditAction] | None = _query_none,
    resource_type: list[ResourceType] | None = _query_none,
    username: str | None = _query_none,
    user_id: uuid.UUID | None = _query_none,
    tenant_id: uuid.UUID | None = _query_none,
    start_time: str | None = _query_none,
    end_time: str | None = _query_none,
    page: int = _query_page,
    page_size: int = _query_page_size,
) -> PageResponse[AuditLogResponse]:
    from datetime import datetime

    params = AuditLogQueryParams(
        action=action or None,
        resource_type=resource_type or None,
        username=username,
        user_id=user_id,
        tenant_id=tenant_id,
        start_time=datetime.fromisoformat(start_time) if start_time else None,
        end_time=datetime.fromisoformat(end_time) if end_time else None,
        page=page,
        page_size=page_size,
    )
    service = AuditService(db)
    items, total = await service.query_logs(params, user)
    log_list = [
        AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            username=username,
            tenant_id=log.tenant_id,
            action=log.action.value,
            resource_type=log.resource_type.value,
            resource_id=log.resource_id,
            detail=log.detail,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            request_id=log.request_id,
            created_at=log.created_at,
        )
        for log, username in items
    ]
    page_data = PageData(items=log_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{log_id}", response_model=BaseResponse[AuditLogResponse])
async def get_audit_log(
    log_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("audit_logs", "read"))],
) -> BaseResponse[AuditLogResponse]:
    service = AuditService(db)
    log, username = await service.get_log(log_id, user)
    data = AuditLogResponse(
        id=log.id,
        user_id=log.user_id,
        username=username,
        tenant_id=log.tenant_id,
        action=log.action.value,
        resource_type=log.resource_type.value,
        resource_id=log.resource_id,
        detail=log.detail,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        request_id=log.request_id,
        created_at=log.created_at,
    )
    return BaseResponse(data=data, message="获取成功")
