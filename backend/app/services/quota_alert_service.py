import logging
import uuid

from sqlalchemy import select
from sqlalchemy import true as sa_true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationPriority, NotificationType, UserRole
from app.models.user import User
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class QuotaAlertService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_and_alert(
        self,
        tenant_id: uuid.UUID,
        gpu_usage_percent: float,
        tenant_name: str = "",
    ) -> int:
        if gpu_usage_percent <= 85:
            return 0

        result = await self.db.execute(
            select(User.id).where(
                User.tenant_id == tenant_id,
                User.role.in_([UserRole.ADMIN]),
                User.is_active == sa_true(),
            )
        )
        admin_ids = [row[0] for row in result.all()]
        if not admin_ids:
            return 0

        notif_service = NotificationService(self.db)
        notifications = await notif_service.create_notification_for_users(
            user_ids=admin_ids,
            tenant_id=tenant_id,
            type=NotificationType.QUOTA_ALERT,
            title="GPU 配额告警",
            content=f"租户「{tenant_name}」GPU 使用率已达 {gpu_usage_percent:.1f}%, 超过 85% 告警阈值。",
            priority=NotificationPriority.HIGH,
            resource_type="quota",
            resource_id=str(tenant_id),
        )
        return len(notifications)
