import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.enums import TenantStatus, UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantCreateRequest, TenantQuotaUpdateRequest, TenantUpdateRequest

logger = logging.getLogger(__name__)


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant(self, req: TenantCreateRequest) -> Tenant:
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

        namespace = make_namespace_name(str(tenant.id))
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
        return tenant

    async def list_tenants(self, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
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

    async def get_tenant_detail(self, tenant_id: uuid.UUID) -> dict:
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

    async def update_tenant(self, tenant_id: uuid.UUID, req: TenantUpdateRequest) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        if req.display_name is not None:
            tenant.display_name = req.display_name
        if req.description is not None:
            tenant.description = req.description
        await self.db.flush()
        await self.db.refresh(tenant)
        return tenant
        # TODO: 审计日志 — 租户信息更新 (Story 2.5)

    async def toggle_tenant_status(self, tenant_id: uuid.UUID, target_status: TenantStatus) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        if tenant.status == target_status:
            if target_status == TenantStatus.DISABLED:
                raise ConflictException("租户已被禁用")
            raise ConflictException("租户已处于启用状态")
        tenant.status = target_status
        await self.db.flush()
        await self.db.refresh(tenant)
        return tenant
        # TODO: 审计日志 — 租户状态变更 (Story 2.5)

    async def delete_tenant(self, tenant_id: uuid.UUID) -> None:
        tenant = await self.get_tenant(tenant_id)
        member_count_result = await self.db.execute(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        )
        member_count = member_count_result.scalar_one()
        if member_count > 0:
            raise ConflictException("请先移除租户下的所有成员")

        namespace = tenant.k8s_namespace_name
        if namespace:
            for delete_fn, label in [
                (lambda ns=namespace: delete_resource_quota(ns), "ResourceQuota"),
                (lambda ns=namespace: delete_network_policy(ns), "NetworkPolicy"),
                (lambda ns=namespace: delete_namespace(ns), "Namespace"),
            ]:
                try:
                    delete_fn()
                except Exception:
                    logger.warning("删除 K8s %s 失败: namespace=%s", label, namespace, exc_info=True)

        await self.db.delete(tenant)
        await self.db.flush()
        # TODO: 审计日志 — 租户删除 (Story 2.5)

    async def update_quota(self, tenant_id: uuid.UUID, req: TenantQuotaUpdateRequest) -> Tenant:
        tenant = await self.get_tenant(tenant_id)

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

        # TODO: 审计日志 — 配额调整 (Story 2.5)
        return tenant

    async def get_quota_usage(self, tenant_id: uuid.UUID) -> dict:
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

    async def list_members(self, tenant_id: uuid.UUID) -> list[dict]:
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
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, new_role: UserRole, current_user_id: uuid.UUID
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

        user.role = new_role
        await self.db.flush()
        await self.db.refresh(user)
        return user
        # TODO: 审计日志 — 成员角色变更 (Story 2.5)

    async def remove_member(self, tenant_id: uuid.UUID, user_id: uuid.UUID, current_user_id: uuid.UUID) -> None:
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
        # TODO: 审计日志 — 成员移除 (Story 2.5)
