from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.clients import get_harbor_client
from app.core.config import settings
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.integrations.base import K8S_NAMESPACE_PREFIX, sanitize_k8s_name
from app.integrations.k8s import job as k8s_job
from app.integrations.k8s import secret as k8s_secret
from app.models.enums import AuditAction, BuildStatus, ResourceType
from app.models.image import Image
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class ImageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_tenant_name(self, tenant_id: uuid.UUID) -> str:
        from app.models.tenant import Tenant

        result = await self.db.execute(select(Tenant.name).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在")
        return tenant

    async def list_images(
        self,
        keyword: str | None = None,
        source: str | None = None,
        category: str | None = None,
        tenant_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Image], int]:
        query = select(Image).where(Image.deleted_at.is_(None))

        if tenant_id is not None:
            query = query.where((Image.tenant_id == tenant_id) | (Image.tenant_id.is_(None)))
        if keyword:
            query = query.where(Image.name.ilike(f"%{keyword}%"))
        if source:
            query = query.where(Image.source == source)
        if category:
            query = query.where(Image.category == category)

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(Image.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_image(self, image_id: uuid.UUID) -> Image:
        return await self._get_image_or_fail(image_id)

    async def list_selectable_images(self, tenant_id: uuid.UUID, *, category: str | None = None) -> list[Image]:
        stmt = select(Image).where(
            Image.deleted_at.is_(None),
            Image.is_enabled.is_(True),
            or_(
                and_(Image.source == "preset", Image.tenant_id.is_(None)),
                and_(
                    Image.source == "custom",
                    Image.tenant_id == tenant_id,
                    Image.build_status == BuildStatus.SUCCEEDED,
                ),
            ),
        )
        if category:
            stmt = stmt.where(Image.category == category)
        stmt = stmt.order_by(
            case((Image.source == "preset", 0), else_=1),
            Image.created_at.desc(),
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_image(
        self,
        name: str,
        tag: str,
        image_ref: str,
        description: str | None = None,
        source: str = "preset",
        category: str = "training",
        audit_context: dict[str, Any] | None = None,
    ) -> Image:
        existing = await self.db.execute(
            select(Image).where(
                Image.image_ref == image_ref,
                Image.category == category,
                Image.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictException("镜像地址已存在")

        image = Image(
            name=name,
            tag=tag,
            image_ref=image_ref,
            description=description,
            source=source,
            category=category,
            is_enabled=True,
        )
        self.db.add(image)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"镜像 '{name}:{tag}' 在该分类下已存在, 请更换名称或标签") from exc

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
            target_category = kwargs.get("category") or image.category
            existing = await self.db.execute(
                select(Image).where(
                    Image.image_ref == kwargs["image_ref"],
                    Image.category == target_category,
                    Image.id != image_id,
                    Image.deleted_at.is_(None),
                )
            )
            if existing.scalar_one_or_none():
                raise ConflictException("镜像地址已存在")

        for key, value in kwargs.items():
            if value is not None:
                setattr(image, key, value)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"镜像 '{image.name}:{image.tag}' 在该分类下已存在, 请更换名称或标签") from exc

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

    async def build_image(
        self,
        dockerfile: str,
        name: str,
        tag: str,
        description: str | None,
        tenant_id: uuid.UUID,
        category: str = "training",
        audit_context: dict[str, Any] | None = None,
    ) -> Image:
        """创建镜像构建记录 (仅 DB 操作, 构建由 Taskiq worker 异步执行)."""
        if not dockerfile.strip():
            raise BadRequestException("Dockerfile 内容不能为空")

        image = Image(
            name=name,
            tag=tag,
            image_ref=f"pending-{name}:{tag}",
            description=description,
            source="custom",
            category=category,
            tenant_id=tenant_id,
            build_status=BuildStatus.PENDING,
            dockerfile=dockerfile,
            is_enabled=False,
        )
        self.db.add(image)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"镜像 '{name}:{tag}' 在该分类下已存在, 请更换名称或标签") from exc

        await self.db.refresh(image)

        # 设置 build_job_name (K8s 资源名, 确定性生成)
        job_name = k8s_job.make_job_name(name)
        image.build_job_name = job_name

        if audit_context:
            await self._log_audit(
                action=AuditAction.BUILD,
                resource_id=str(image.id),
                detail={"name": name},
                **audit_context,
            )

        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def execute_image_build(self, image_id: uuid.UUID, tenant_id: uuid.UUID) -> Image:
        """由 Taskiq worker 调用: 执行 Harbor + K8s 镜像构建操作链."""
        image = await self._get_image_or_fail(image_id)
        tenant_name = await self._get_tenant_name(tenant_id)
        namespace = f"{K8S_NAMESPACE_PREFIX}{sanitize_k8s_name(tenant_name)}"
        cm_name = k8s_job.make_configmap_name(image.name)
        job_name = image.build_job_name or k8s_job.make_job_name(image.name)

        try:
            harbor_project = f"{settings.HARBOR_PROJECT_PREFIX}{sanitize_k8s_name(tenant_name)}"
            await get_harbor_client().ensure_project(harbor_project)

            harbor_dockerconfig = get_harbor_client().make_harbor_dockerconfig()
            await k8s_secret.create_secret(
                namespace=namespace,
                name=k8s_job.HARBOR_SECRET_NAME,
                data=harbor_dockerconfig,
            )

            await k8s_job.create_configmap(
                namespace=namespace,
                name=cm_name,
                data={"Dockerfile": image.dockerfile or ""},
            )

            destination = get_harbor_client().make_harbor_image_ref(
                tenant_name=tenant_name,
                name=image.name,
                tag=image.tag,
            )
            job_obj = k8s_job.create_build_job(
                namespace=namespace,
                job_name=job_name,
                dockerfile_configmap=cm_name,
                destination=destination,
                harbor_url=settings.HARBOR_URL,
            )
            await k8s_job.submit_job(namespace=namespace, job=job_obj)

            image.build_job_name = job_name
            await self.db.commit()
            await self.db.refresh(image)
        except Exception:
            image.build_status = BuildStatus.FAILED
            await self.db.commit()
            raise

        return image

    async def get_build_log(self, image_id: uuid.UUID) -> str:
        image = await self._get_image_or_fail(image_id)

        if not image.build_job_name or not image.tenant_id:
            return ""

        tenant_name = await self._get_tenant_name(image.tenant_id)
        namespace = f"{K8S_NAMESPACE_PREFIX}{sanitize_k8s_name(tenant_name)}"
        return await k8s_job.get_job_logs(namespace=namespace, job_name=image.build_job_name)

    async def rebuild_image(
        self,
        image_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> Image:
        """标记镜像重新构建 (仅 DB 操作, 构建由 Taskiq worker 异步执行)."""
        image = await self._get_image_or_fail(image_id)

        if image.source != "custom":
            raise BadRequestException("仅自定义镜像支持重新构建")
        if not image.tenant_id:
            raise BadRequestException("镜像缺少租户信息")
        if image.build_status not in (BuildStatus.FAILED, BuildStatus.SUCCEEDED):
            raise BadRequestException("仅失败或已完成的镜像可重新构建")

        image.build_status = BuildStatus.PENDING
        image.is_enabled = False
        image.build_job_name = k8s_job.make_job_name(image.name)
        await self.db.flush()

        if audit_context:
            await self._log_audit(
                action=AuditAction.REBUILD,
                resource_id=str(image.id),
                detail={"name": image.name},
                **audit_context,
            )

        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def execute_image_rebuild(self, image_id: uuid.UUID, tenant_id: uuid.UUID) -> Image:
        """由 Taskiq worker 调用: 清理旧 K8s 资源 + 重新执行 Harbor + K8s 构建操作链."""
        image = await self._get_image_or_fail(image_id)
        tenant_name = await self._get_tenant_name(tenant_id)
        namespace = f"{K8S_NAMESPACE_PREFIX}{sanitize_k8s_name(tenant_name)}"

        # 清理旧的构建资源
        old_cm_name = k8s_job.make_configmap_name(image.name)
        try:
            await k8s_job.delete_configmap(namespace=namespace, name=old_cm_name)
        except Exception:
            logger.warning("Failed to delete old ConfigMap %s in rebuild", old_cm_name, exc_info=True)
        if image.build_job_name:
            try:
                await k8s_job.delete_job(namespace=namespace, job_name=image.build_job_name)
            except Exception:
                logger.warning("Failed to delete old Job %s in rebuild", image.build_job_name, exc_info=True)

        job_name = k8s_job.make_job_name(image.name)
        cm_name = k8s_job.make_configmap_name(image.name)

        try:
            harbor_project = f"{settings.HARBOR_PROJECT_PREFIX}{sanitize_k8s_name(tenant_name)}"
            await get_harbor_client().ensure_project(harbor_project)

            harbor_dockerconfig = get_harbor_client().make_harbor_dockerconfig()
            await k8s_secret.create_secret(
                namespace=namespace,
                name=k8s_job.HARBOR_SECRET_NAME,
                data=harbor_dockerconfig,
            )

            await k8s_job.create_configmap(
                namespace=namespace,
                name=cm_name,
                data={"Dockerfile": image.dockerfile or ""},
            )

            destination = get_harbor_client().make_harbor_image_ref(
                tenant_name=tenant_name,
                name=image.name,
                tag=image.tag,
            )
            job_obj = k8s_job.create_build_job(
                namespace=namespace,
                job_name=job_name,
                dockerfile_configmap=cm_name,
                destination=destination,
                harbor_url=settings.HARBOR_URL,
            )
            await k8s_job.submit_job(namespace=namespace, job=job_obj)

            image.build_job_name = job_name
            await self.db.commit()
            await self.db.refresh(image)
        except Exception:
            image.build_status = BuildStatus.FAILED
            await self.db.commit()
            raise

        return image

    async def sync_build_status(self, image: Image) -> Image:
        if not image.build_job_name or not image.tenant_id:
            return image
        if image.build_status in (BuildStatus.SUCCEEDED, BuildStatus.FAILED):
            return image

        tenant_name = await self._get_tenant_name(image.tenant_id)
        namespace = f"{K8S_NAMESPACE_PREFIX}{sanitize_k8s_name(tenant_name)}"
        status = await k8s_job.get_job_status(namespace=namespace, job_name=image.build_job_name)

        if status.get("status") == "succeeded":
            image.build_status = BuildStatus.PUSHING
            destination = get_harbor_client().make_harbor_image_ref(
                tenant_name=tenant_name,
                name=image.name,
                tag=image.tag,
            )
            image.image_ref = destination
            image.build_status = BuildStatus.SUCCEEDED
            image.is_enabled = True
        elif status.get("status") == "failed":
            image.build_status = BuildStatus.FAILED
        elif status.get("status") == "running":
            image.build_status = BuildStatus.BUILDING
        else:
            image.build_status = BuildStatus.PENDING

        if image.build_status in (BuildStatus.SUCCEEDED, BuildStatus.FAILED):
            cm_name = k8s_job.make_configmap_name(image.name)
            try:
                await k8s_job.delete_configmap(namespace=namespace, name=cm_name)
            except Exception:
                logger.warning("Failed to delete ConfigMap %s in namespace %s", cm_name, namespace, exc_info=True)

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(image)
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
