import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.models.enums import NotificationType
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.notification import NotificationResponse, UnreadCountResponse
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])

_OptType = Annotated[NotificationType | None, Query()]
_Page = Annotated[int, Query(ge=1)]
_PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("", response_model=PageResponse[NotificationResponse])
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("notifications", "read"))],
    type: _OptType = None,
    page: _Page = 1,
    page_size: _PageSize = 20,
    unread: bool = False,
) -> PageResponse[NotificationResponse]:
    service = NotificationService(db)
    items, total = await service.list_notifications(
        user_id=user.id,
        type=type,
        page=page,
        page_size=page_size,
        unread_only=unread,
    )
    notif_list = [
        NotificationResponse(
            id=n.id,
            user_id=n.user_id,
            tenant_id=n.tenant_id,
            type=n.type,
            title=n.title,
            content=n.content,
            priority=n.priority,
            is_read=n.is_read,
            resource_type=n.resource_type,
            resource_id=n.resource_id,
            created_at=n.created_at,
        )
        for n in items
    ]
    page_data = PageData(items=notif_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/unread-count", response_model=BaseResponse[UnreadCountResponse])
async def get_unread_count(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("notifications", "read"))],
) -> BaseResponse[UnreadCountResponse]:
    service = NotificationService(db)
    count = await service.get_unread_count(user.id)
    return BaseResponse(data=UnreadCountResponse(count=count), message="获取成功")


@router.post("/read-all", response_model=BaseResponse[dict[str, Any]])
async def mark_all_as_read(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("notifications", "write"))],
) -> BaseResponse[dict[str, Any]]:
    service = NotificationService(db)
    count = await service.mark_all_as_read(user.id)
    return BaseResponse(data={"updated_count": count}, message="全部标记为已读")


@router.post("/{notification_id}/read", response_model=BaseResponse[NotificationResponse])
async def mark_as_read(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("notifications", "write"))],
) -> BaseResponse[NotificationResponse]:
    service = NotificationService(db)
    n = await service.mark_as_read(notification_id, user.id)
    data = NotificationResponse(
        id=n.id,
        user_id=n.user_id,
        tenant_id=n.tenant_id,
        type=n.type,
        title=n.title,
        content=n.content,
        priority=n.priority,
        is_read=n.is_read,
        resource_type=n.resource_type,
        resource_id=n.resource_id,
        created_at=n.created_at,
    )
    return BaseResponse(data=data, message="标记已读成功")
