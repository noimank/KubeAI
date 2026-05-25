from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

import structlog
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.core.security import create_access_token, decode_token
from app.core.ws_pubsub import get_ws_pubsub
from app.integrations.base import sanitize_k8s_name
from app.integrations.jupyterhub.client import get_jupyterhub_client
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.network_policy import create_tenant_network_policy
from app.integrations.k8s.pvc import (
    create_pvc,
    make_dataset_pvc_name,
    make_user_home_host_path,
    make_workspace_host_path,
    pvc_exists,
)
from app.integrations.k8s.resource_quota import get_quota_used
from app.integrations.k8s.secret import ensure_registry_pull_secret
from app.models.dataset import Dataset, DatasetVersion
from app.models.dev_environment import DevEnvironment
from app.models.dev_environment_image import DevEnvironmentImage
from app.models.enums import DevEnvironmentStatus
from app.models.tenant import Tenant
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.dev_environment import DatasetMountRequest

logger = structlog.get_logger(__name__)

TERMINAL_STATUSES = {DevEnvironmentStatus.FAILED, DevEnvironmentStatus.STOPPED}
STARTUP_MISSING_SERVER_GRACE_SECONDS = 180
KUBEAI_CONTAINER_ROOT = "/kubeai"


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
        environment_image_id: uuid.UUID,
        gpu_count: int = 0,
        cpu: str = "2",
        memory: str = "4Gi",
        description: str | None = None,
        env_vars: dict[str, str] | None = None,
        datasets: list[DatasetMountRequest] | None = None,
    ) -> DevEnvironment:
        dev_image = await self._get_dev_environment_image(environment_image_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if gpu_count > 0:
            await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_count)

        workspace_host_path = make_workspace_host_path(tenant.name)
        user_home_host_path = make_user_home_host_path(username)
        sanitized_username = sanitize_k8s_name(username)
        home_path = self._home_path()
        workspace_path = self._workspace_path()

        extra_volumes, extra_volume_mounts, mounted_datasets_info = await self._build_volumes(
            datasets=datasets,
            tenant_id=tenant_id,
            namespace=namespace,
            workspace_host_path=workspace_host_path,
            user_home_host_path=user_home_host_path,
            username=username,
            sanitized_username=sanitized_username,
        )

        env = DevEnvironment(
            tenant_id=tenant_id,
            created_by=user_id,
            name=name,
            image=dev_image.image_ref,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            status=DevEnvironmentStatus.PENDING,
            description=description,
            env_vars=env_vars,
            mounted_datasets=mounted_datasets_info if mounted_datasets_info else None,
            environment_image_id=dev_image.id,
            environment_type=dev_image.environment_type,
        )
        env.spawner_name = self._make_spawner_name(username=username, user_id=user_id, env_id=env.id)
        self.db.add(env)
        await self.db.flush()

        jh_client = get_jupyterhub_client()
        try:
            await create_tenant_network_policy(namespace)
            pull_secret_name = await ensure_registry_pull_secret(namespace)
            await jh_client.ensure_user(env.spawner_name)
            await jh_client.start_server(
                env.spawner_name,
                image=dev_image.image_ref,
                cpu=cpu,
                memory=memory,
                gpu_count=gpu_count,
                namespace=namespace,
                extra_volumes=extra_volumes or None,
                extra_volume_mounts=extra_volume_mounts or None,
                environment_type=dev_image.environment_type,
                env_vars=self._build_env_vars(env, env_vars, workspace_path=workspace_path, home_path=home_path),
                image_pull_secret=pull_secret_name,
            )
        except Exception as e:
            logger.error("start_server_failed", spawner=env.spawner_name, error=str(e))
            try:
                await jh_client.delete_user(env.spawner_name)
            except Exception:
                logger.warning("cleanup_jupyterhub_user_failed", spawner=env.spawner_name)
            env.status = DevEnvironmentStatus.FAILED
            env.error_message = f"启动失败: {e}"
            await self.db.commit()
            raise ExternalServiceException(f"启动失败: {e}") from e

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

        non_terminal = [e for e in environments if e.spawner_name and e.status not in TERMINAL_STATUSES]
        if non_terminal:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            for env in non_terminal:
                try:
                    await self._sync_environment_status(env, namespace)
                except Exception as e:
                    logger.warning("sync_status_failed", spawner=env.spawner_name, error=str(e))
            await self.db.commit()
            for env in non_terminal:
                await self.db.refresh(env)

        return environments, total

    async def get_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        env = await self._get_environment_or_fail(env_id, tenant_id)
        if env.spawner_name and env.status not in TERMINAL_STATUSES:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            try:
                await self._sync_environment_status(env, namespace)
            except Exception as e:
                logger.warning("sync_status_failed", spawner=env.spawner_name, error=str(e))
            await self.db.commit()
            await self.db.refresh(env)
        return env

    async def stop_environment(
        self, env_id: uuid.UUID, tenant_id: uuid.UUID, *, stopped_reason: str = "manual"
    ) -> DevEnvironment:
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status not in (
            DevEnvironmentStatus.RUNNING,
            DevEnvironmentStatus.CREATING,
            DevEnvironmentStatus.PENDING,
        ):
            raise ConflictException(f"当前状态为 {env.status}, 无法停止环境")

        if env.spawner_name:
            jh_client = get_jupyterhub_client()
            try:
                await jh_client.stop_server(env.spawner_name)
            except Exception as e:
                logger.warning("stop_server_failed", spawner=env.spawner_name, error=str(e))

        env.status = DevEnvironmentStatus.STOPPED
        env.stopped_reason = stopped_reason
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

        user = await self._get_user_or_fail(env.created_by)
        workspace_host_path = make_workspace_host_path(tenant.name)
        user_home_host_path = make_user_home_host_path(user.username)
        sanitized_username = sanitize_k8s_name(user.username)
        home_path = self._home_path()
        workspace_path = self._workspace_path()

        extra_volumes, extra_volume_mounts, _ = await self._build_volumes(
            datasets=None,
            tenant_id=tenant_id,
            namespace=namespace,
            workspace_host_path=workspace_host_path,
            user_home_host_path=user_home_host_path,
            username=user.username,
            sanitized_username=sanitized_username,
            mounted_datasets=env.mounted_datasets,
        )

        jh_client = get_jupyterhub_client()
        try:
            await create_tenant_network_policy(namespace)
            pull_secret_name = await ensure_registry_pull_secret(namespace)
            await jh_client.ensure_user(env.spawner_name or "")
            await jh_client.start_server(
                env.spawner_name or "",
                image=env.image,
                cpu=env.cpu,
                memory=env.memory,
                gpu_count=env.gpu_count,
                namespace=namespace,
                extra_volumes=extra_volumes or None,
                extra_volume_mounts=extra_volume_mounts or None,
                environment_type=env.environment_type,
                env_vars=self._build_env_vars(env, env.env_vars, workspace_path=workspace_path, home_path=home_path),
                image_pull_secret=pull_secret_name,
            )
        except Exception as e:
            logger.error("start_server_failed", spawner=env.spawner_name, error=str(e))
            env.status = DevEnvironmentStatus.FAILED
            env.error_message = f"启动失败: {e}"
            await self.db.commit()
            raise ExternalServiceException(f"启动失败: {e}") from e

        env.status = DevEnvironmentStatus.CREATING
        env.error_message = None
        await self.db.commit()
        await self.db.refresh(env)
        return env

    async def delete_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.spawner_name:
            jh_client = get_jupyterhub_client()
            try:
                await jh_client.stop_server(env.spawner_name)
            except Exception as e:
                logger.warning("stop_server_failed", spawner=env.spawner_name, error=str(e))
            try:
                await jh_client.delete_user(env.spawner_name)
            except Exception as e:
                logger.warning("delete_user_failed", spawner=env.spawner_name, error=str(e))

        await self.db.delete(env)
        await self.db.commit()
        return env

    async def create_open_ticket(self, env_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status != DevEnvironmentStatus.RUNNING:
            raise ConflictException("环境未运行, 无法获取访问地址")

        if not env.spawner_name:
            raise ConflictException("环境未关联 Spawner")

        if not settings.JUPYTERHUB_BASE_URL:
            raise ExternalServiceException("未配置 JupyterHub 访问地址")

        expires_delta = timedelta(seconds=max(30, settings.DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS))
        return create_access_token(
            {
                "sub": str(user_id),
                "purpose": "dev_environment_open",
                "env_id": str(env.id),
                "tenant_id": str(env.tenant_id),
                "spawner_name": env.spawner_name,
            },
            expires_delta=expires_delta,
        )

    async def build_hub_login_url_from_ticket(
        self,
        ticket: str,
        expected_env_id: uuid.UUID,
        *,
        login_token: str,
    ) -> tuple[str, str]:
        env = await self._get_open_environment_from_ticket(ticket, expected_env_id)
        if not settings.JUPYTERHUB_BASE_URL:
            raise ExternalServiceException("未配置 JupyterHub 访问地址")

        next_url = self._build_user_redirect_url(env.environment_type)
        login_url = f"{settings.JUPYTERHUB_BASE_URL.rstrip('/')}/hub/login"
        return f"{login_url}?{urlencode({'login_token': login_token, 'next': next_url})}", env.spawner_name or ""

    async def _get_open_environment_from_ticket(self, ticket: str, expected_env_id: uuid.UUID) -> DevEnvironment:
        try:
            payload = decode_token(ticket)
        except ValueError:
            raise ConflictException("访问票据无效或已过期") from None

        if payload.get("purpose") != "dev_environment_open":
            raise ConflictException("访问票据无效")

        try:
            env_id = uuid.UUID(str(payload["env_id"]))
            tenant_id = uuid.UUID(str(payload["tenant_id"]))
        except (KeyError, ValueError, TypeError):
            raise ConflictException("访问票据无效") from None
        if env_id != expected_env_id:
            raise ConflictException("访问票据无效")

        env = await self._get_environment_or_fail(env_id, tenant_id)
        spawner_name = payload.get("spawner_name")
        if env.status != DevEnvironmentStatus.RUNNING or not env.spawner_name or spawner_name != env.spawner_name:
            raise ConflictException("环境未运行, 无法获取访问地址")

        return env

    def _normalize_access_url(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        if settings.JUPYTERHUB_BASE_URL:
            return f"{settings.JUPYTERHUB_BASE_URL.rstrip('/')}/{url.lstrip('/')}"
        return url

    def _build_user_redirect_url(self, environment_type: str | None) -> str:
        base_url = "/hub/user-redirect/"
        if environment_type == "jupyter":
            return f"{base_url}lab"
        if environment_type == "vscode":
            return f"{base_url}codeserver/"
        if environment_type == "rstudio":
            return f"{base_url}rstudio/"
        return base_url

    async def _build_volumes(
        self,
        *,
        datasets: list[DatasetMountRequest] | None,
        tenant_id: uuid.UUID,
        namespace: str,
        workspace_host_path: str,
        user_home_host_path: str,
        username: str,
        sanitized_username: str,
        mounted_datasets: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]] | None]:
        extra_volumes: list[dict[str, Any]] = []
        extra_volume_mounts: list[dict[str, Any]] = []
        mounted_datasets_info: list[dict[str, Any]] = []

        home_path = self._home_path()
        workspace_path = self._workspace_path()

        extra_volumes.append(
            {"name": "home-volume", "hostPath": {"path": user_home_host_path, "type": "DirectoryOrCreate"}}
        )
        extra_volume_mounts.append({"name": "home-volume", "mountPath": home_path})

        extra_volumes.append(
            {"name": "workspace-volume", "hostPath": {"path": workspace_host_path, "type": "DirectoryOrCreate"}}
        )
        extra_volume_mounts.append({"name": "workspace-volume", "mountPath": workspace_path})

        if datasets:
            for dm in datasets:
                dataset, version = await self._resolve_dataset_mount(dm.dataset_id, dm.version_id, tenant_id)
                ds_pvc_name = make_dataset_pvc_name(dataset.name, version.version_number)
                mount_path = self._dataset_mount_path(dataset.name, version.version_number)

                if not await pvc_exists(namespace, ds_pvc_name):
                    size_bytes = version.total_size_bytes or 0
                    size_gb = max(1, -(-size_bytes // (1024**3)))
                    await create_pvc(namespace, ds_pvc_name, f"{size_gb}Gi")

                vol_name = f"dataset-{sanitize_k8s_name(dataset.name)}-v{version.version_number}"
                extra_volumes.append({"name": vol_name, "persistentVolumeClaim": {"claimName": ds_pvc_name}})
                extra_volume_mounts.append({"name": vol_name, "mountPath": mount_path, "readOnly": True})

                mounted_datasets_info.append(
                    {
                        "dataset_id": str(dataset.id),
                        "dataset_name": dataset.name,
                        "version_id": str(version.id),
                        "version_number": version.version_number,
                        "pvc_name": ds_pvc_name,
                        "mount_path": mount_path,
                    }
                )
        elif mounted_datasets:
            for md in mounted_datasets:
                version_number = int(md["version_number"])
                mount_path = self._dataset_mount_path(md["dataset_name"], version_number)
                md["mount_path"] = mount_path
                vol_name = f"dataset-{sanitize_k8s_name(md['dataset_name'])}-v{version_number}"
                extra_volumes.append({"name": vol_name, "persistentVolumeClaim": {"claimName": md["pvc_name"]}})
                extra_volume_mounts.append({"name": vol_name, "mountPath": mount_path, "readOnly": True})

        return extra_volumes, extra_volume_mounts, mounted_datasets_info or None

    async def _sync_environment_status(self, env: DevEnvironment, namespace: str) -> None:
        if not env.spawner_name:
            return

        jh_client = get_jupyterhub_client()
        user_data = await jh_client.get_user(env.spawner_name)
        if user_data is None:
            self._mark_missing_server_status(env, "JupyterHub 用户不存在, 启动可能已被清理")
            return

        server_data = user_data.get("servers", {}).get("", {})
        if not server_data:
            self._mark_missing_server_status(env, "JupyterHub 未返回 Server 信息, 启动可能已被清理")
            return

        new_status = jh_client.map_server_status(server_data if server_data else None)

        if new_status == DevEnvironmentStatus.RUNNING:
            server_url = server_data.get("url") if server_data else None
            if server_url:
                env.access_url = self._normalize_access_url(cast("str", server_url))
            jh_last_activity = server_data.get("last_activity") if server_data else None
            if jh_last_activity:
                env.last_active_at = jh_last_activity
            else:
                env.last_active_at = datetime.now(UTC).isoformat()
            env.error_message = None
            env.stopped_reason = None

        if new_status != env.status:
            old_status = env.status
            logger.info(
                "dev_environment_status_changed",
                env_id=str(env.id),
                old_status=old_status,
                new_status=new_status,
            )
            env.status = new_status
            self._publish_status_change(env.tenant_id, env.id, old_status, new_status.value)

    def _mark_missing_server_status(self, env: DevEnvironment, message: str) -> None:
        if env.status in (DevEnvironmentStatus.PENDING, DevEnvironmentStatus.CREATING):
            if self._startup_age_seconds(env) < STARTUP_MISSING_SERVER_GRACE_SECONDS:
                return
            env.status = DevEnvironmentStatus.FAILED
            env.error_message = f"启动超时: {message}"
            return

        if env.status == DevEnvironmentStatus.RUNNING:
            env.status = DevEnvironmentStatus.STOPPED
            env.stopped_reason = env.stopped_reason or "server_missing"

    def _startup_age_seconds(self, env: DevEnvironment) -> float:
        reference = env.updated_at or env.created_at
        if reference is None:
            return STARTUP_MISSING_SERVER_GRACE_SECONDS
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        return (datetime.now(UTC) - reference).total_seconds()

    def _build_env_vars(
        self,
        env: DevEnvironment,
        user_env_vars: dict[str, str] | None,
        *,
        workspace_path: str | None = None,
        home_path: str | None = None,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        if user_env_vars:
            merged.update(user_env_vars)
        if settings.BACKEND_API_URL:
            merged["KUBEAI_API_URL"] = settings.BACKEND_API_URL
        merged["KUBEAI_ENV_ID"] = str(env.id)
        merged["KUBEAI_ROOT_PATH"] = KUBEAI_CONTAINER_ROOT
        if workspace_path:
            merged["KUBEAI_WORKSPACE_PATH"] = workspace_path
        if home_path:
            merged["KUBEAI_HOME_PATH"] = home_path
        return merged

    def _home_path(self) -> str:
        return f"{KUBEAI_CONTAINER_ROOT}/home"

    def _workspace_path(self) -> str:
        return f"{KUBEAI_CONTAINER_ROOT}/workspace"

    def _dataset_mount_path(self, dataset_name: str, version_number: int) -> str:
        return f"{KUBEAI_CONTAINER_ROOT}/datasets/{sanitize_k8s_name(dataset_name)}/v{version_number}"

    def _make_spawner_name(self, *, username: str, user_id: uuid.UUID, env_id: uuid.UUID) -> str:
        return f"devenv-{sanitize_k8s_name(username, max_length=40)}-{str(user_id)[:8]}-{str(env_id)[:8]}"

    async def _get_dev_environment_image(self, image_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironmentImage:
        from sqlalchemy import or_

        stmt = select(DevEnvironmentImage).where(
            DevEnvironmentImage.id == image_id,
            DevEnvironmentImage.deleted_at.is_(None),
            DevEnvironmentImage.is_enabled.is_(True),
            or_(
                DevEnvironmentImage.tenant_id.is_(None),
                DevEnvironmentImage.tenant_id == tenant_id,
            ),
        )
        result = await self.db.execute(stmt)
        img = result.scalar_one_or_none()
        if not img:
            raise NotFoundException("开发环境镜像不存在或未启用")
        return img

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

    async def _get_user_or_fail(self, user_id: uuid.UUID) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")
        return user

    async def _resolve_dataset_mount(
        self, dataset_id: uuid.UUID, version_id: uuid.UUID | None, tenant_id: uuid.UUID
    ) -> tuple[Dataset, DatasetVersion]:
        ds_stmt = select(Dataset).where(Dataset.id == dataset_id, Dataset.tenant_id == tenant_id)
        dataset = (await self.db.execute(ds_stmt)).scalar_one_or_none()
        if not dataset:
            raise NotFoundException("数据集不存在")

        if version_id:
            ver_stmt = select(DatasetVersion).where(
                DatasetVersion.id == version_id, DatasetVersion.dataset_id == dataset_id
            )
        else:
            ver_stmt = (
                select(DatasetVersion)
                .where(DatasetVersion.dataset_id == dataset_id)
                .order_by(DatasetVersion.version_number.desc())
                .limit(1)
            )
        version = (await self.db.execute(ver_stmt)).scalar_one_or_none()
        if not version:
            raise NotFoundException("数据集版本不存在")

        return dataset, version

    @staticmethod
    def _publish_status_change(
        tenant_id: uuid.UUID,
        env_id: uuid.UUID,
        old_status: str,
        new_status: str,
    ) -> None:
        pubsub = get_ws_pubsub()
        if pubsub is None:
            return
        import asyncio

        _task = asyncio.ensure_future(  # noqa: RUF006
            pubsub.publish(
                tenant_id=tenant_id,
                event="dev_environment.status_changed",
                payload={"id": str(env_id), "old_status": old_status, "new_status": new_status},
            )
        )
