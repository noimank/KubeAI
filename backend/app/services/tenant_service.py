from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.integrations.k8s.namespace import create_namespace, delete_namespace, make_namespace_name
from app.integrations.k8s.network_policy import create_tenant_network_policy, delete_network_policy
from app.integrations.k8s.resource_quota import (
    build_tenant_resource_quota,
    create_resource_quota,
    delete_resource_quota,
    get_cluster_capacity,
    get_quota_used,
    update_resource_quota,
)
from app.models.enums import AuditAction, ResourceType, TenantStatus, UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.tenant import TenantCreateRequest, TenantQuotaUpdateRequest, TenantUpdateRequest

logger = logging.getLogger(__name__)


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant(self, req: TenantCreateRequest, audit_context: dict[str, Any] | None = None) -> Tenant:
        existing = await self.db.execute(select(Tenant).where(Tenant.name == req.name))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("租户名称已存在")

        tenant = Tenant(
            name=req.name,
            display_name=req.display_name,
            description=req.description,
        )
        self.db.add(tenant)
        await self.db.flush()

        namespace = make_namespace_name(tenant.name)
        try:
            create_namespace(namespace)
            try:
                quota = build_tenant_resource_quota(
                    gpu_limit=tenant.gpu_limit,
                    cpu_limit=tenant.cpu_limit,
                    memory_limit=tenant.memory_limit,
                    storage_limit=tenant.storage_limit,
                )
                create_resource_quota(namespace, quota)
                create_tenant_network_policy(namespace)
            except Exception:
                delete_resource_quota(namespace)
                delete_network_policy(namespace)
                delete_namespace(namespace)
                raise
        except ConflictException:
            raise
        except Exception as e:
            await self.db.rollback()
            raise ExternalServiceException(f"K8s 资源创建失败: {e}") from e

        tenant.k8s_namespace_name = namespace
        await self.db.flush()
        await self.db.refresh(tenant)

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.CREATE,
                resource_type=ResourceType.TENANT,
                resource_id=str(tenant.id),
                detail={"name": tenant.name, "display_name": tenant.display_name, "description": tenant.description},
                tenant_id=tenant.id,
                **audit_context,
            )

        return tenant

    async def list_tenants(self, page: int = 1, page_size: int = 20) -> tuple[list[dict[str, Any]], int]:
        count_result = await self.db.execute(select(func.count()).select_from(Tenant))
        total = count_result.scalar_one()

        member_subq = (
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == Tenant.id)
            .correlate(Tenant)
            .scalar_subquery()
        )

        query = (
            select(Tenant, member_subq.label("member_count"))
            .order_by(Tenant.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        rows = result.all()

        items = []
        for tenant, member_count in rows:
            items.append(
                {
                    "id": tenant.id,
                    "name": tenant.name,
                    "display_name": tenant.display_name,
                    "description": tenant.description,
                    "status": tenant.status,
                    "k8s_namespace_name": tenant.k8s_namespace_name,
                    "gpu_limit": tenant.gpu_limit,
                    "cpu_limit": tenant.cpu_limit,
                    "memory_limit": tenant.memory_limit,
                    "storage_limit": tenant.storage_limit,
                    "member_count": member_count,
                    "created_at": tenant.created_at,
                    "updated_at": tenant.updated_at,
                }
            )
        return items, total

    async def get_tenant(self, tenant_id: uuid.UUID) -> Tenant:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在")
        return tenant

    async def get_tenant_detail(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = await self.get_tenant(tenant_id)
        member_count_result = await self.db.execute(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        )
        member_count = member_count_result.scalar_one()
        return {
            "id": tenant.id,
            "name": tenant.name,
            "display_name": tenant.display_name,
            "description": tenant.description,
            "status": tenant.status,
            "k8s_namespace_name": tenant.k8s_namespace_name,
            "gpu_limit": tenant.gpu_limit,
            "cpu_limit": tenant.cpu_limit,
            "memory_limit": tenant.memory_limit,
            "storage_limit": tenant.storage_limit,
            "member_count": member_count,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
        }

    async def update_tenant(
        self, tenant_id: uuid.UUID, req: TenantUpdateRequest, audit_context: dict[str, Any] | None = None
    ) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        old_display_name = tenant.display_name
        old_description = tenant.description
        if req.display_name is not None:
            tenant.display_name = req.display_name
        if req.description is not None:
            tenant.description = req.description
        await self.db.flush()
        await self.db.refresh(tenant)

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.TENANT,
                resource_id=str(tenant.id),
                detail={
                    "old": {"display_name": old_display_name, "description": old_description},
                    "new": {"display_name": tenant.display_name, "description": tenant.description},
                },
                tenant_id=tenant.id,
                **audit_context,
            )

        return tenant

    async def toggle_tenant_status(
        self, tenant_id: uuid.UUID, target_status: TenantStatus, audit_context: dict[str, Any] | None = None
    ) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        if tenant.status == target_status:
            if target_status == TenantStatus.DISABLED:
                raise ConflictException("租户已被禁用")
            raise ConflictException("租户已处于启用状态")
        old_status = tenant.status
        tenant.status = target_status
        await self.db.flush()
        await self.db.refresh(tenant)

        if audit_context:
            audit_svc = AuditService(self.db)
            action = AuditAction.ENABLE if target_status == TenantStatus.ACTIVE else AuditAction.DISABLE
            await audit_svc.log_action(
                action=action,
                resource_type=ResourceType.TENANT,
                resource_id=str(tenant.id),
                detail={"old_status": old_status.value, "new_status": target_status.value},
                tenant_id=tenant.id,
                **audit_context,
            )

        return tenant

    async def delete_tenant(self, tenant_id: uuid.UUID, audit_context: dict[str, Any] | None = None) -> None:
        tenant = await self.get_tenant(tenant_id)
        member_count_result = await self.db.execute(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        )
        member_count = member_count_result.scalar_one()
        if member_count > 0:
            raise ConflictException("请先移除租户下的所有成员")

        namespace = tenant.k8s_namespace_name
        if namespace:
            cleanup_ops: list[tuple[Callable[[], None], str]] = [
                (lambda: delete_resource_quota(namespace), "ResourceQuota"),
                (lambda: delete_network_policy(namespace), "NetworkPolicy"),
                (lambda: delete_namespace(namespace), "Namespace"),
            ]
            for delete_fn, label in cleanup_ops:
                try:
                    delete_fn()
                except Exception:
                    logger.warning("删除 K8s %s 失败: namespace=%s", label, namespace, exc_info=True)

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.DELETE,
                resource_type=ResourceType.TENANT,
                resource_id=str(tenant.id),
                detail={"name": tenant.name, "display_name": tenant.display_name},
                tenant_id=tenant.id,
                **audit_context,
            )

        await self.db.delete(tenant)
        await self.db.flush()

    async def update_quota(
        self, tenant_id: uuid.UUID, req: TenantQuotaUpdateRequest, audit_context: dict[str, Any] | None = None
    ) -> Tenant:
        tenant = await self.get_tenant(tenant_id)

        old_gpu = tenant.gpu_limit
        old_cpu = tenant.cpu_limit
        old_memory = tenant.memory_limit
        old_storage = tenant.storage_limit

        if not tenant.k8s_namespace_name:
            raise BadRequestException("租户尚未完成 K8s 命名空间初始化")

        # AC2: 校验不超过集群总量
        try:
            capacity = get_cluster_capacity()
            cluster_gpu = int(capacity["gpu"])
            if req.gpu_limit > cluster_gpu:
                raise QuotaExceededException(f"GPU 配额超过集群可用资源(集群总量 {cluster_gpu} 张)")
        except QuotaExceededException:
            raise
        except Exception as e:
            logger.warning("获取集群容量失败: %s", e, exc_info=True)
            raise ExternalServiceException(f"无法获取集群资源信息: {e}") from e

        # AC3: 校验使用量不超过新配额
        if not req.force:
            try:
                used = get_quota_used(tenant.k8s_namespace_name)
                gpu_used = int(used.get("requests.nvidia.com/gpu", "0"))
                if gpu_used > req.gpu_limit:
                    raise QuotaExceededException(
                        f"当前 GPU 使用量为 {gpu_used} 张, 新配额 {req.gpu_limit} 张将低于使用量"
                    )
            except QuotaExceededException:
                raise
            except Exception as e:
                logger.warning("获取配额使用量失败: %s", e, exc_info=True)

        # 更新 DB
        tenant.gpu_limit = req.gpu_limit
        tenant.cpu_limit = req.cpu_limit
        tenant.memory_limit = req.memory_limit
        tenant.storage_limit = req.storage_limit
        await self.db.flush()
        await self.db.refresh(tenant)

        # 同步 K8s
        try:
            update_resource_quota(
                namespace=tenant.k8s_namespace_name,
                gpu_limit=tenant.gpu_limit,
                cpu_limit=tenant.cpu_limit,
                memory_limit=tenant.memory_limit,
                storage_limit=tenant.storage_limit,
            )
        except Exception as e:
            logger.error("同步 K8s ResourceQuota 失败: %s", e, exc_info=True)
            raise ExternalServiceException(f"K8s 配额同步失败: {e}") from e

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.UPDATE_QUOTA,
                resource_type=ResourceType.QUOTA,
                resource_id=str(tenant.id),
                detail={
                    "old_quota": {"gpu": old_gpu, "cpu": old_cpu, "memory": old_memory, "storage": old_storage},
                    "new_quota": {
                        "gpu": tenant.gpu_limit,
                        "cpu": tenant.cpu_limit,
                        "memory": tenant.memory_limit,
                        "storage": tenant.storage_limit,
                    },
                },
                tenant_id=tenant.id,
                **audit_context,
            )

        return tenant

    async def get_quota_usage(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = await self.get_tenant(tenant_id)

        if not tenant.k8s_namespace_name:
            return {"gpu_used": 0, "cpu_used": "0", "memory_used": "0", "storage_used": "0"}

        try:
            used = get_quota_used(tenant.k8s_namespace_name)
            return {
                "gpu_used": int(used.get("requests.nvidia.com/gpu", "0")),
                "cpu_used": used.get("requests.cpu", "0"),
                "memory_used": used.get("requests.memory", "0"),
                "storage_used": used.get("requests.storage", "0"),
            }
        except Exception as e:
            logger.warning("获取配额使用量失败: %s", e, exc_info=True)
            raise ExternalServiceException(f"无法获取配额使用量: {e}") from e

    # --- Member Management ---

    async def add_member(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role: UserRole,
        audit_context: dict[str, Any] | None = None,
    ) -> User:
        await self.get_tenant(tenant_id)

        result = await self.db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")
        if user.tenant_id == tenant_id:
            raise ConflictException("该用户已在此租户中")
        if user.tenant_id is not None:
            raise ConflictException("该用户已属于其他租户, 请先将其移出原租户")

        user.tenant_id = tenant_id
        user.role = role
        await self.db.flush()
        await self.db.refresh(user)

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.ADD_MEMBER,
                resource_type=ResourceType.MEMBERSHIP,
                resource_id=str(user.id),
                detail={"username": user.username, "email": user.email, "role": role.value},
                tenant_id=tenant_id,
                **audit_context,
            )

        return user

    async def list_members(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        await self.get_tenant(tenant_id)
        result = await self.db.execute(
            select(User).where(User.tenant_id == tenant_id, User.deleted_at.is_(None)).order_by(User.created_at.asc())
        )
        users = result.scalars().all()
        return [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "joined_at": user.created_at,
            }
            for user in users
        ]

    async def update_member_role(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        new_role: UserRole,
        current_user_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> User:
        if user_id == current_user_id:
            raise BadRequestException("不能修改自己的角色")
        if new_role == UserRole.ADMIN:
            raise BadRequestException("不能将成员角色设为管理员")

        result = await self.db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("该用户不属于此租户")

        old_role = user.role
        user.role = new_role
        await self.db.flush()
        await self.db.refresh(user)

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.UPDATE_ROLE,
                resource_type=ResourceType.MEMBERSHIP,
                resource_id=str(user.id),
                detail={"old_role": old_role.value, "new_role": new_role.value},
                tenant_id=tenant_id,
                **audit_context,
            )

        return user

    async def remove_member(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        current_user_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        if user_id == current_user_id:
            raise BadRequestException("不能移除自己")

        result = await self.db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("该用户不属于此租户")

        user.tenant_id = None
        await self.db.flush()

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.REMOVE_MEMBER,
                resource_type=ResourceType.MEMBERSHIP,
                resource_id=str(user.id),
                detail={"username": user.username, "email": user.email},
                tenant_id=tenant_id,
                **audit_context,
            )
