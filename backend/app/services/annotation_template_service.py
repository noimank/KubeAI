from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.integrations.labelstudio.templates import parse_label_config
from app.models.annotation import AnnotationProject
from app.models.annotation_template import AnnotationTemplate
from app.models.enums import AuditAction, ResourceType
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AnnotationTemplateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _log_audit(
        self,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: str,
        detail: dict[str, Any] | None = None,
        tenant_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> None:
        await AuditService(self.db).log_action(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            tenant_id=tenant_id,
            **kwargs,
        )

    def _validate_label_config(self, label_config: str) -> None:
        """仅校验 XML 合法性, 不再存储 annotation_type."""
        parse_label_config(label_config)

    async def list_templates(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        name: str | None = None,
        tag: str | None = None,
        group: str | None = None,
    ) -> tuple[list[AnnotationTemplate], int]:
        base = select(AnnotationTemplate).where(AnnotationTemplate.tenant_id == tenant_id)
        if name:
            base = base.where(AnnotationTemplate.name.ilike(f"%{name}%"))
        if tag:
            base = base.where(AnnotationTemplate.tags.contains([tag]))
        if group:
            base = base.where(AnnotationTemplate.group == group)

        total = (await self.db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (
            (
                await self.db.execute(
                    base.order_by(AnnotationTemplate.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def get_groups(self, tenant_id: uuid.UUID) -> list[str]:
        rows = await self.db.execute(
            select(AnnotationTemplate.group)
            .where(AnnotationTemplate.tenant_id == tenant_id)
            .distinct()
            .order_by(AnnotationTemplate.group)
        )
        return [r for (r,) in rows.all() if r]

    async def get_template(self, template_id: uuid.UUID, tenant_id: uuid.UUID) -> AnnotationTemplate:
        result = await self.db.execute(
            select(AnnotationTemplate).where(
                AnnotationTemplate.id == template_id,
                AnnotationTemplate.tenant_id == tenant_id,
            )
        )
        tpl = result.scalar_one_or_none()
        if tpl is None:
            raise NotFoundException("标注模板不存在")
        return tpl

    async def create_template(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        label_config: str,
        tags: list[str],
        group: str = "其他",
        audit_context: dict[str, Any] | None = None,
    ) -> AnnotationTemplate:
        self._validate_label_config(label_config)
        tpl = AnnotationTemplate(
            tenant_id=tenant_id,
            user_id=user_id,
            name=name.strip(),
            description=description,
            label_config=label_config,
            tags=tags,
            group=group.strip() or "其他",
        )
        self.db.add(tpl)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"标注模板名称 '{name.strip()}' 已存在, 请更换名称") from exc

        await self.db.refresh(tpl)

        if audit_context:
            await self._log_audit(
                action=AuditAction.CREATE,
                resource_type=ResourceType.ANNOTATION_TEMPLATE,
                resource_id=str(tpl.id),
                detail={
                    "name": tpl.name,
                    "group": tpl.group,
                },
                tenant_id=tenant_id,
                **audit_context,
            )
        await self.db.commit()
        return tpl

    async def update_template(
        self,
        template_id: uuid.UUID,
        tenant_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        label_config: str | None = None,
        tags: list[str] | None = None,
        group: str | None = None,
        audit_context: dict[str, Any] | None = None,
    ) -> AnnotationTemplate:
        tpl = await self.get_template(template_id, tenant_id)
        if name is not None:
            tpl.name = name.strip()
        if description is not None:
            tpl.description = description
        if tags is not None:
            tpl.tags = tags
        if group is not None:
            tpl.group = group.strip() or "其他"
        if label_config is not None:
            self._validate_label_config(label_config)
            tpl.label_config = label_config
        if not any(x is not None for x in (name, description, tags, label_config, group)):
            raise AppException("至少需要传入一个可编辑字段", status_code=400)

        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"标注模板名称 '{tpl.name}' 已存在, 请更换名称") from exc

        await self.db.refresh(tpl)

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ANNOTATION_TEMPLATE,
                resource_id=str(tpl.id),
                detail={"name": tpl.name},
                tenant_id=tenant_id,
                **audit_context,
            )
        return tpl

    async def delete_template(
        self,
        template_id: uuid.UUID,
        tenant_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        tpl = await self.get_template(template_id, tenant_id)

        # 引用保护: 已有项目引用此模板则禁止删除 (DB 层 ON DELETE SET NULL 是保底)
        ref_count = (
            await self.db.execute(
                select(func.count())
                .select_from(AnnotationProject)
                .where(
                    AnnotationProject.template_id == template_id,
                    AnnotationProject.tenant_id == tenant_id,
                )
            )
        ).scalar_one()
        if ref_count > 0:
            raise AppException(
                f"模板被 {ref_count} 个项目引用, 请先解绑或归档项目",
                status_code=409,
            )

        name = tpl.name
        await self.db.delete(tpl)
        await self.db.flush()

        if audit_context:
            await self._log_audit(
                action=AuditAction.DELETE,
                resource_type=ResourceType.ANNOTATION_TEMPLATE,
                resource_id=str(template_id),
                detail={"name": name},
                tenant_id=tenant_id,
                **audit_context,
            )
