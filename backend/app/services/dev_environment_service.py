from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.integrations.base import sanitize_k8s_name
from app.integrations.jupyterhub.client import get_jupyterhub_client
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.pvc import create_pvc, delete_pvc
from app.integrations.k8s.resource_quota import get_quota_used
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus
from app.models.tenant import Tenant

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {DevEnvironmentStatus.FAILED, DevEnvironmentStatus.STOPPED}
NON_TERMINAL_STATUSES = {
    DevEnvironmentStatus.PENDING,
    DevEnvironmentStatus.CREATING,
    DevEnvironmentStatus.RUNNING,
}


class DevEnvironmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_environment(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        username: str,
        name: str,
        image: str,
        gpu_count: int = 0,
        cpu: str = "2",
        memory: str = "4Gi",
        description: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> DevEnvironment:
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if gpu_count > 0:
            await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_count)

        jupyterhub_user = f"devenv-{sanitize_k8s_name(username)}-{str(user_id)[:8]}"
        pvc_name = f"workspace-{sanitize_k8s_name(username)}-{str(user_id)[:8]}"

        try:
            await create_pvc(
                namespace=namespace,
                pvc_name=pvc_name,
                storage_request="10Gi",
                access_mode="ReadWriteOnce",
            )
        except Exception as e:
            logger.error("Failed to create PVC %s: %s", pvc_name, e)

        env = DevEnvironment(
            tenant_id=tenant_id,
            created_by=user_id,
            name=name,
            image=image,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            status=DevEnvironmentStatus.PENDING,
            jupyterhub_user=jupyterhub_user,
            pvc_name=pvc_name,
            description=description,
            env_vars=env_vars,
        )
        self.db.add(env)
        await self.db.flush()

        jh_client = get_jupyterhub_client()
        try:
            await jh_client.ensure_user(jupyterhub_user)
            await jh_client.start_server(
                jupyterhub_user,
                image=image,
                cpu=cpu,
                memory=memory,
                gpu_count=gpu_count,
                pvc_name=pvc_name,
                env_vars=env_vars,
            )
        except Exception as e:
            logger.error("Failed to start JupyterHub server for %s: %s", jupyterhub_user, e)
            env.status = DevEnvironmentStatus.FAILED
            env.error_message = f"JupyterHub 启动失败: {e}"
            await self.db.commit()
            raise ExternalServiceException(f"JupyterHub 启动失败: {e}") from e

        env.status = DevEnvironmentStatus.CREATING
        await self.db.commit()
        await self.db.refresh(env)
        return env

    async def list_environments(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        name: str | None = None,
    ) -> tuple[list[DevEnvironment], int]:
        query = select(DevEnvironment).where(DevEnvironment.tenant_id == tenant_id)

        if user_id is not None:
            query = query.where(DevEnvironment.created_by == user_id)
        if status:
            query = query.where(DevEnvironment.status == status)
        if name:
            query = query.where(DevEnvironment.name.ilike(f"%{name}%"))

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(DevEnvironment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        environments = list(result.scalars().all())

        non_terminal = [e for e in environments if e.jupyterhub_user and e.status not in TERMINAL_STATUSES]
        if non_terminal:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            for env in non_terminal:
                try:
                    await self._sync_environment_status(env, namespace)
                except Exception as e:
                    logger.warning("Failed to sync status for %s: %s", env.jupyterhub_user, e)
            await self.db.commit()
            for env in non_terminal:
                await self.db.refresh(env)

        return environments, total

    async def get_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        env = await self._get_environment_or_fail(env_id, tenant_id)
        if env.jupyterhub_user and env.status not in TERMINAL_STATUSES:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            try:
                await self._sync_environment_status(env, namespace)
            except Exception as e:
                logger.warning("Failed to sync status for %s: %s", env.jupyterhub_user, e)
            await self.db.commit()
            await self.db.refresh(env)
        return env

    async def stop_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status not in (
            DevEnvironmentStatus.RUNNING,
            DevEnvironmentStatus.CREATING,
            DevEnvironmentStatus.PENDING,
        ):
            raise ConflictException(f"当前状态为 {env.status}, 无法停止环境")

        if env.jupyterhub_user:
            jh_client = get_jupyterhub_client()
            try:
                await jh_client.stop_server(env.jupyterhub_user)
            except Exception as e:
                logger.warning("Failed to stop JupyterHub server for %s: %s", env.jupyterhub_user, e)

        env.status = DevEnvironmentStatus.STOPPED
        await self.db.commit()
        await self.db.refresh(env)
        return env

    async def start_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status != DevEnvironmentStatus.STOPPED:
            raise ConflictException(f"当前状态为 {env.status}, 只有已停止的环境才能启动")

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if env.gpu_count > 0:
            await self._check_gpu_quota(namespace, tenant.gpu_limit, env.gpu_count)

        jh_client = get_jupyterhub_client()
        try:
            await jh_client.start_server(
                env.jupyterhub_user or "",
                image=env.image,
                cpu=env.cpu,
                memory=env.memory,
                gpu_count=env.gpu_count,
                pvc_name=env.pvc_name,
                env_vars=env.env_vars,
            )
        except Exception as e:
            logger.error("Failed to start JupyterHub server for %s: %s", env.jupyterhub_user, e)
            env.status = DevEnvironmentStatus.FAILED
            env.error_message = f"JupyterHub 启动失败: {e}"
            await self.db.commit()
            raise ExternalServiceException(f"JupyterHub 启动失败: {e}") from e

        env.status = DevEnvironmentStatus.CREATING
        env.error_message = None
        await self.db.commit()
        await self.db.refresh(env)
        return env

    async def delete_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        env = await self._get_environment_or_fail(env_id, tenant_id)

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if env.jupyterhub_user:
            jh_client = get_jupyterhub_client()
            try:
                await jh_client.stop_server(env.jupyterhub_user)
            except Exception as e:
                logger.warning("Failed to stop JupyterHub server for %s: %s", env.jupyterhub_user, e)
            try:
                await jh_client.delete_user(env.jupyterhub_user)
            except Exception as e:
                logger.warning("Failed to delete JupyterHub user %s: %s", env.jupyterhub_user, e)

        if env.pvc_name:
            try:
                await delete_pvc(namespace, env.pvc_name)
            except Exception as e:
                logger.warning("Failed to delete PVC %s: %s", env.pvc_name, e)

        await self.db.delete(env)
        await self.db.commit()
        return env

    async def get_notebook_url(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status != DevEnvironmentStatus.RUNNING:
            raise ConflictException("环境未运行, 无法获取 Notebook URL")

        if env.notebook_url:
            return env.notebook_url

        if not env.jupyterhub_user:
            raise ConflictException("环境未关联 JupyterHub 用户")

        base_url = settings.JUPYTERHUB_BASE_URL
        if not base_url:
            jh_client = get_jupyterhub_client()
            user_data = await jh_client.get_user(env.jupyterhub_user)
            if user_data:
                server_data = user_data.get("servers", {}).get("", {})
                url = cast("str", server_data.get("url"))
                if url:
                    env.notebook_url = url
                    await self.db.commit()
                    await self.db.refresh(env)
                    return url
            raise ExternalServiceException("无法获取 Notebook URL")

        notebook_url = f"{base_url.rstrip('/')}/user/{env.jupyterhub_user}/"
        env.notebook_url = notebook_url
        await self.db.commit()
        await self.db.refresh(env)
        return notebook_url

    async def _sync_environment_status(self, env: DevEnvironment, namespace: str) -> None:
        if not env.jupyterhub_user:
            return

        jh_client = get_jupyterhub_client()
        user_data = await jh_client.get_user(env.jupyterhub_user)
        if user_data is None:
            env.status = DevEnvironmentStatus.STOPPED
            return

        server_data = user_data.get("servers", {}).get("", {})
        new_status = jh_client.map_server_status(server_data if server_data else None)

        if new_status == DevEnvironmentStatus.RUNNING:
            server_url = server_data.get("url") if server_data else None
            if server_url:
                env.notebook_url = server_url

        if new_status != env.status:
            logger.info(
                "dev_environment_status_changed",
                extra={
                    "env_id": str(env.id),
                    "old_status": env.status,
                    "new_status": new_status,
                },
            )
            env.status = new_status

    async def _check_gpu_quota(self, namespace: str, gpu_limit: int, requested: int) -> None:
        if requested == 0:
            return
        if gpu_limit <= 0:
            raise QuotaExceededException("租户 GPU 配额为 0, 无法创建需要 GPU 的开发环境")
        try:
            used = await get_quota_used(namespace)
            gpu_used = int(used.get("requests.nvidia.com/gpu", "0"))
        except Exception:
            gpu_used = 0
        if gpu_used + requested > gpu_limit:
            raise QuotaExceededException(
                f"GPU 配额不足: 已使用 {gpu_used} 张, 配额 {gpu_limit} 张, 请求 {requested} 张"
            )

    async def _get_environment_or_fail(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        result = await self.db.execute(
            select(DevEnvironment).where(DevEnvironment.id == env_id, DevEnvironment.tenant_id == tenant_id)
        )
        env = result.scalar_one_or_none()
        if not env:
            raise NotFoundException("开发环境不存在")
        return env

    async def _get_tenant_or_fail(self, tenant_id: uuid.UUID) -> Tenant:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在")
        return tenant
