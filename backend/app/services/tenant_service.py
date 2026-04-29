import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ExternalServiceException
from app.integrations.k8s.namespace import create_namespace, delete_namespace, make_namespace_name
from app.integrations.k8s.network_policy import create_tenant_network_policy, delete_network_policy
from app.integrations.k8s.resource_quota import (
    build_tenant_resource_quota,
    create_resource_quota,
    delete_resource_quota,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantCreateRequest

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
