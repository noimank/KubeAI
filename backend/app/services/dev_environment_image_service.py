from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictException, NotFoundException
from app.models.dev_environment_image import DevEnvironmentImage
from app.models.enums import AuditAction, ResourceType
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class DevEnvironmentImageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_images(
        self,
        *,
        keyword: str | None = None,
        environment_type: str | None = None,
        tenant_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DevEnvironmentImage], int]:
        query = select(DevEnvironmentImage).where(DevEnvironmentImage.deleted_at.is_(None))

        if tenant_id is not None:
            query = query.where(
                or_(DevEnvironmentImage.tenant_id == tenant_id, DevEnvironmentImage.tenant_id.is_(None))
            )
        if keyword:
            query = query.where(DevEnvironmentImage.name.ilike(f"%{keyword}%"))
        if environment_type:
            query = query.where(DevEnvironmentImage.environment_type == environment_type)

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(DevEnvironmentImage.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_image(self, image_id: uuid.UUID) -> DevEnvironmentImage:
        return await self._get_image_or_fail(image_id)

    async def list_selectable_images(self, tenant_id: uuid.UUID) -> list[DevEnvironmentImage]:
        stmt = (
            select(DevEnvironmentImage)
            .where(
                DevEnvironmentImage.deleted_at.is_(None),
                DevEnvironmentImage.is_enabled.is_(True),
                or_(DevEnvironmentImage.tenant_id.is_(None), DevEnvironmentImage.tenant_id == tenant_id),
            )
            .order_by(DevEnvironmentImage.environment_type, DevEnvironmentImage.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_image(
        self,
        *,
        name: str,
        environment_type: str,
        image_ref: str,
        description: str | None = None,
        icon: str | None = None,
        default_cpu: str = "2",
        default_memory: str = "4Gi",
        default_gpu_count: int = 0,
        tenant_id: uuid.UUID | None = None,
        audit_context: dict[str, Any] | None = None,
    ) -> DevEnvironmentImage:
        img = DevEnvironmentImage(
            name=name,
            environment_type=environment_type,
            image_ref=image_ref,
            description=description,
            icon=icon,
            default_cpu=default_cpu,
            default_memory=default_memory,
            default_gpu_count=default_gpu_count,
            is_enabled=True,
            tenant_id=tenant_id,
        )
        self.db.add(img)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"开发环境镜像 '{name}' (类型: {environment_type}) 已存在, 请更换名称") from exc

        await self.db.refresh(img)

        if audit_context:
            await self._log_audit(
                action=AuditAction.CREATE,
                resource_id=str(img.id),
                detail={"name": name, "environment_type": environment_type, "image_ref": image_ref},
                **audit_context,
            )

        await self.db.commit()
        return img

    async def update_image(
        self,
        image_id: uuid.UUID,
        *,
        audit_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> DevEnvironmentImage:
        img = await self._get_image_or_fail(image_id)

        for key, value in kwargs.items():
            if value is not None:
                setattr(img, key, value)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(
                f"开发环境镜像 '{img.name}' (类型: {img.environment_type}) 已存在, 请更换名称"
            ) from exc

        await self.db.refresh(img)

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_id=str(img.id),
                detail={"name": img.name, "updated_fields": list(kwargs.keys())},
                **audit_context,
            )

        await self.db.commit()
        return img

    async def delete_image(
        self,
        image_id: uuid.UUID,
        *,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        img = await self._get_image_or_fail(image_id)

        if audit_context:
            await self._log_audit(
                action=AuditAction.DELETE,
                resource_id=str(img.id),
                detail={"name": img.name, "image_ref": img.image_ref},
                **audit_context,
            )

        img.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()

    async def toggle_image(
        self,
        image_id: uuid.UUID,
        *,
        audit_context: dict[str, Any] | None = None,
    ) -> DevEnvironmentImage:
        img = await self._get_image_or_fail(image_id)
        img.is_enabled = not img.is_enabled
        await self.db.flush()
        await self.db.refresh(img)

        if audit_context:
            action = AuditAction.ENABLE if img.is_enabled else AuditAction.DISABLE
            await self._log_audit(
                action=action,
                resource_id=str(img.id),
                detail={"name": img.name, "is_enabled": img.is_enabled},
                **audit_context,
            )

        await self.db.commit()
        return img

    async def _get_image_or_fail(self, image_id: uuid.UUID) -> DevEnvironmentImage:
        result = await self.db.execute(
            select(DevEnvironmentImage).where(
                DevEnvironmentImage.id == image_id, DevEnvironmentImage.deleted_at.is_(None)
            )
        )
        img = result.scalar_one_or_none()
        if not img:
            raise NotFoundException("开发环境镜像不存在")
        return img

    async def _log_audit(
        self,
        action: AuditAction,
        resource_id: str,
        detail: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        audit_svc = AuditService(self.db)
        await audit_svc.log_action(
            action=action,
            resource_type=ResourceType.DEV_ENVIRONMENT_IMAGE,
            resource_id=resource_id,
            detail=detail,
            **kwargs,
        )
