import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.ws_pubsub import get_ws_pubsub
from app.models.enums import NotificationPriority, NotificationType
from app.models.notification import Notification


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        type: NotificationType,
        title: str,
        content: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            tenant_id=tenant_id,
            type=type,
            title=title,
            content=content,
            priority=priority,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        self.db.add(notification)
        await self.db.flush()

        self._publish_notification(notification)
        return notification

    async def create_notification_for_users(
        self,
        user_ids: list[uuid.UUID],
        tenant_id: uuid.UUID,
        type: NotificationType,
        title: str,
        content: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> list[Notification]:
        notifications = [
            Notification(
                user_id=uid,
                tenant_id=tenant_id,
                type=type,
                title=title,
                content=content,
                priority=priority,
                resource_type=resource_type,
                resource_id=resource_id,
            )
            for uid in user_ids
        ]
        self.db.add_all(notifications)
        await self.db.flush()

        for n in notifications:
            self._publish_notification(n)

        return notifications

    async def list_notifications(
        self,
        user_id: uuid.UUID,
        type: NotificationType | None = None,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        query = select(Notification).where(Notification.user_id == user_id)

        if unread_only:
            query = query.where(Notification.is_read == False)  # noqa: E712

        if type is not None:
            query = query.where(Notification.type == type)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).where(
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def mark_as_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> Notification:
        result = await self.db.execute(select(Notification).where(Notification.id == notification_id))
        notification = result.scalar_one_or_none()
        if not notification:
            raise NotFoundException("通知不存在")
        if notification.user_id != user_id:
            raise ForbiddenException("无权操作此通知")

        notification.is_read = True
        await self.db.flush()
        return notification

    async def mark_all_as_read(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
            .returning(Notification.id)
        )
        rows = result.fetchall()
        await self.db.flush()
        return len(rows)

    @staticmethod
    def _publish_notification(notification: Notification) -> None:
        pubsub = get_ws_pubsub()
        if pubsub is None:
            return
        import asyncio

        asyncio.ensure_future(  # noqa: RUF006
            pubsub.publish(
                tenant_id=notification.tenant_id,
                event="notification.created",
                payload={
                    "id": str(notification.id),
                    "type": notification.type.value if notification.type else None,
                    "title": notification.title,
                    "resource_type": notification.resource_type,
                    "resource_id": notification.resource_id,
                },
                target_user_id=notification.user_id,
            )
        )
