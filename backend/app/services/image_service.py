from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import AuditAction, ResourceType
from app.models.image import Image
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class ImageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_images(
        self,
        keyword: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Image], int]:
        query = select(Image).where(Image.deleted_at.is_(None))
        if keyword:
            query = query.where(Image.name.ilike(f"%{keyword}%"))
        if source:
            query = query.where(Image.source == source)

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(Image.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_image(self, image_id: uuid.UUID) -> Image:
        return await self._get_image_or_fail(image_id)

    async def create_image(
        self,
        name: str,
        tag: str,
        image_ref: str,
        description: str | None = None,
        source: str = "preset",
        audit_context: dict[str, Any] | None = None,
    ) -> Image:
        existing = await self.db.execute(select(Image).where(Image.image_ref == image_ref, Image.deleted_at.is_(None)))
        if existing.scalar_one_or_none():
            raise ConflictException("镜像地址已存在")

        image = Image(
            name=name,
            tag=tag,
            image_ref=image_ref,
            description=description,
            source=source,
            is_enabled=True,
        )
        self.db.add(image)
        await self.db.flush()
        await self.db.refresh(image)

        if audit_context:
            await self._log_audit(
                action=AuditAction.CREATE,
                resource_id=str(image.id),
                detail={"name": name, "image_ref": image_ref},
                **audit_context,
            )

        await self.db.commit()
        return image

    async def update_image(
        self,
        image_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Image:
        image = await self._get_image_or_fail(image_id)

        if "image_ref" in kwargs and kwargs["image_ref"] != image.image_ref:
            existing = await self.db.execute(
                select(Image).where(
                    Image.image_ref == kwargs["image_ref"],
                    Image.id != image_id,
                    Image.deleted_at.is_(None),
                )
            )
            if existing.scalar_one_or_none():
                raise ConflictException("镜像地址已存在")

        for key, value in kwargs.items():
            if value is not None:
                setattr(image, key, value)
        await self.db.flush()
        await self.db.refresh(image)

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_id=str(image.id),
                detail={"name": image.name, "updated_fields": list(kwargs.keys())},
                **audit_context,
            )

        await self.db.commit()
        return image

    async def delete_image(
        self,
        image_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        image = await self._get_image_or_fail(image_id)

        if audit_context:
            await self._log_audit(
                action=AuditAction.DELETE,
                resource_id=str(image.id),
                detail={"name": image.name, "image_ref": image.image_ref},
                **audit_context,
            )

        from datetime import UTC, datetime

        image.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()

    async def toggle_image(
        self,
        image_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> Image:
        image = await self._get_image_or_fail(image_id)
        image.is_enabled = not image.is_enabled
        await self.db.flush()
        await self.db.refresh(image)

        if audit_context:
            action = AuditAction.ENABLE if image.is_enabled else AuditAction.DISABLE
            await self._log_audit(
                action=action,
                resource_id=str(image.id),
                detail={"name": image.name, "is_enabled": image.is_enabled},
                **audit_context,
            )

        await self.db.commit()
        return image

    async def _get_image_or_fail(self, image_id: uuid.UUID) -> Image:
        result = await self.db.execute(select(Image).where(Image.id == image_id, Image.deleted_at.is_(None)))
        image = result.scalar_one_or_none()
        if not image:
            raise NotFoundException("镜像不存在")
        return image

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
            resource_type=ResourceType.IMAGE,
            resource_id=resource_id,
            detail=detail,
            **kwargs,
        )
