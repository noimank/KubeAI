from __future__ import annotations

import asyncio
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid

import structlog
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.core.ws_pubsub import publish_ws_event
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.dev_pod import dev_access_url, get_dev_pod_manager
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.network_policy import create_tenant_network_policy
from app.integrations.k8s.pvc import (
    make_dataset_host_path,
    make_user_home_host_path,
    make_workspace_host_path,
)
from app.integrations.k8s.resource_quota import get_quota_used
from app.integrations.k8s.secret import ensure_registry_pull_secret
from app.models.algorithm import Algorithm
from app.models.dataset import Dataset, DatasetVersion
from app.models.dev_environment import DevEnvironment
from app.models.dev_environment_image import DevEnvironmentImage
from app.models.enums import DevEnvironmentStatus
from app.models.tenant import Tenant
from app.models.user import User
from app.services.algorithm_storage_service import AlgorithmStorageService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.dev_environment import DatasetMountRequest

logger = structlog.get_logger(__name__)

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
        algorithm_id: uuid.UUID | None = None,
    ) -> DevEnvironment:
        env, tenant = await self._create_environment_record(
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            name=name,
            environment_image_id=environment_image_id,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            description=description,
            env_vars=env_vars,
            datasets=datasets,
        )
        await self._provision_environment(
            env=env,
            tenant=tenant,
            username=username,
            algorithm_id=algorithm_id,
        )
        await self.db.refresh(env)
        return env

    async def create_environment_record(
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
        env, _ = await self._create_environment_record(
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            name=name,
            environment_image_id=environment_image_id,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            description=description,
            env_vars=env_vars,
            datasets=datasets,
        )
        return env

    async def _create_environment_record(
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
    ) -> tuple[DevEnvironment, Tenant]:
        dev_image = await self._get_dev_environment_image(environment_image_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if gpu_count > 0:
            await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_count)

        workspace_host_path = make_workspace_host_path(tenant.name)
        user_home_host_path = make_user_home_host_path(username)
        sanitized_username = sanitize_k8s_name(username)

        _, _, mounted_datasets_info = await self._build_volumes(
            datasets=datasets,
            tenant_id=tenant_id,
            tenant_name=tenant.name,
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
        await self.db.commit()
        await self.db.refresh(env)
        return env, tenant

    async def provision_environment(
        self,
        env_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        algorithm_id: uuid.UUID | None = None,
    ) -> DevEnvironment:
        env = await self._get_environment_or_fail(env_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        user = await self._get_user_or_fail(env.created_by)
        return await self._provision_environment(
            env=env,
            tenant=tenant,
            username=user.username,
            algorithm_id=algorithm_id,
        )

    async def _provision_environment(
        self,
        *,
        env: DevEnvironment,
        tenant: Tenant,
        username: str,
        algorithm_id: uuid.UUID | None = None,
    ) -> DevEnvironment:
        if env.status not in (DevEnvironmentStatus.PENDING, DevEnvironmentStatus.CREATING):
            logger.info("skip_dev_environment_provision", env_id=str(env.id), status=env.status)
            return env

        old_status = env.status
        env.status = DevEnvironmentStatus.CREATING
        env.error_message = None
        await self.db.commit()
        if old_status != env.status:
            await self._publish_status_change(env.tenant_id, env.id, old_status, env.status)

        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if env.gpu_count > 0:
            await self._check_gpu_quota(namespace, tenant.gpu_limit, env.gpu_count)

        workspace_host_path = make_workspace_host_path(tenant.name)
        user_home_host_path = make_user_home_host_path(username)
        sanitized_username = sanitize_k8s_name(username)
        home_path = self._home_path()
        workspace_path = self._workspace_path()

        extra_volumes, extra_volume_mounts, _ = await self._build_volumes(
            datasets=None,
            tenant_id=env.tenant_id,
            tenant_name=tenant.name,
            namespace=namespace,
            workspace_host_path=workspace_host_path,
            user_home_host_path=user_home_host_path,
            username=username,
            sanitized_username=sanitized_username,
            mounted_datasets=env.mounted_datasets,
        )

        if algorithm_id:
            await self._extract_algorithm_to_home(
                algorithm_id=algorithm_id,
                tenant_id=env.tenant_id,
                user_home_host_path=user_home_host_path,
            )

        pod_mgr = get_dev_pod_manager()
        try:
            await create_tenant_network_policy(namespace)
            pull_secret_name = await ensure_registry_pull_secret(namespace)

            final_env_vars = self._build_env_vars(
                env, env.env_vars, workspace_path=workspace_path, home_path=home_path, algorithm_id=algorithm_id
            )

            await pod_mgr.create(
                env_id=env.id,
                namespace=namespace,
                image=env.image,
                environment_type=env.environment_type,
                cpu=env.cpu,
                memory=env.memory,
                gpu_count=env.gpu_count,
                env_vars=final_env_vars,
                volumes=extra_volumes or [],
                volume_mounts=extra_volume_mounts or [],
                image_pull_secret=pull_secret_name,
                node_selector={"kubeai": "true"},
            )
        except Exception as e:
            logger.error("start_server_failed", env_id=str(env.id), error=str(e))
            try:
                await pod_mgr.delete(env.id, namespace)
            except Exception:
                logger.warning("cleanup_dev_pod_failed", env_id=str(env.id))
            await self.db.rollback()
            try:
                env = await self._get_environment_or_fail(env.id, env.tenant_id)
            except Exception as refresh_error:
                logger.warning(
                    "reload_environment_after_start_failure_failed",
                    env_id=str(env.id),
                    error=str(refresh_error),
                )
            if env.status == DevEnvironmentStatus.STOPPED:
                return env
            old_status = env.status
            env.status = DevEnvironmentStatus.FAILED
            env.error_message = f"启动失败: {e}"
            await self.db.commit()
            if old_status != env.status:
                await self._publish_status_change(env.tenant_id, env.id, old_status, env.status)
            raise ExternalServiceException(f"启动失败: {e}") from e

        await self.db.refresh(env)
        if env.status == DevEnvironmentStatus.STOPPED:
            try:
                pod_mgr = get_dev_pod_manager()
                await pod_mgr.stop_server(env.id, namespace)
            except Exception:
                logger.warning("stop_server_after_user_stop_failed", env_id=str(env.id))
            return env

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
        """纯 DB 列表查询. 状态同步由 sync_dev_environment_statuses_task 周期任务负责."""
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
        return list(result.scalars().all()), total

    async def get_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        """纯 DB 详情查询. 状态同步由 sync_dev_environment_statuses_task 周期任务负责."""
        return await self._get_environment_or_fail(env_id, tenant_id)

    async def sync_non_terminal_environments(self, *, limit: int = 200) -> int:
        result = await self.db.execute(
            select(DevEnvironment)
            .where(
                DevEnvironment.status.in_(
                    [DevEnvironmentStatus.PENDING, DevEnvironmentStatus.CREATING, DevEnvironmentStatus.RUNNING]
                )
            )
            .order_by(DevEnvironment.updated_at.asc())
            .limit(limit)
        )
        environments = list(result.scalars().all())
        if not environments:
            return 0

        tenant_ids = {env.tenant_id for env in environments}
        tenants_result = await self.db.execute(select(Tenant).where(Tenant.id.in_(tenant_ids)))
        tenants = {tenant.id: tenant for tenant in tenants_result.scalars().all()}

        synced_count = 0
        for env in environments:
            tenant = tenants.get(env.tenant_id)
            if tenant is None:
                continue
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            try:
                await self._sync_environment_status(env, namespace)
                synced_count += 1
            except Exception as e:
                logger.warning("sync_status_failed", env_id=str(env.id), error=str(e))

        await self.db.commit()
        return synced_count

    async def stop_environment(
        self, env_id: uuid.UUID, tenant_id: uuid.UUID, *, stopped_reason: str = "manual"
    ) -> DevEnvironment:
        """API 路径: 仅做状态校验 + 置 PENDING (作为停止中过渡), 由 task 负责真实停止."""
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status not in (
            DevEnvironmentStatus.RUNNING,
            DevEnvironmentStatus.CREATING,
            DevEnvironmentStatus.PENDING,
        ):
            raise ConflictException(f"当前状态为 {env.status}, 无法停止环境")

        env.status = DevEnvironmentStatus.PENDING
        env.error_message = None
        await self.db.commit()
        await self.db.refresh(env)
        return env

    async def stop_environment_async(
        self, env_id: uuid.UUID, tenant_id: uuid.UUID, *, stopped_reason: str = "manual"
    ) -> None:
        """真实停止 dev pod, 由 task 调用."""
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status not in (
            DevEnvironmentStatus.RUNNING,
            DevEnvironmentStatus.CREATING,
            DevEnvironmentStatus.PENDING,
        ):
            logger.info("skip_dev_environment_stop", env_id=str(env.id), status=env.status)
            return

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        pod_mgr = get_dev_pod_manager()
        try:
            await pod_mgr.stop_server(env.id, namespace)
        except Exception as e:
            logger.warning("stop_server_failed", env_id=str(env.id), error=str(e))

        env.status = DevEnvironmentStatus.STOPPED
        env.stopped_reason = stopped_reason
        await self.db.commit()
        await self.db.refresh(env)

    async def start_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        """API 路径: 仅做状态校验 + 置 CREATING (作为启动中过渡), 由 task 负责真实启动."""
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status != DevEnvironmentStatus.STOPPED:
            raise ConflictException(f"当前状态为 {env.status}, 只有已停止的环境才能启动")

        env.status = DevEnvironmentStatus.CREATING
        env.error_message = None
        await self.db.commit()
        await self.db.refresh(env)
        return env

    async def start_environment_async(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """真实启动 dev pod, 由 task 调用."""
        env = await self._get_environment_or_fail(env_id, tenant_id)

        if env.status != DevEnvironmentStatus.STOPPED:
            logger.info("skip_dev_environment_start", env_id=str(env.id), status=env.status)
            return

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
            tenant_name=tenant.name,
            namespace=namespace,
            workspace_host_path=workspace_host_path,
            user_home_host_path=user_home_host_path,
            username=user.username,
            sanitized_username=sanitized_username,
            mounted_datasets=env.mounted_datasets,
        )

        pod_mgr = get_dev_pod_manager()
        try:
            await create_tenant_network_policy(namespace)
            pull_secret_name = await ensure_registry_pull_secret(namespace)

            final_env_vars = self._build_env_vars(env, env.env_vars, workspace_path=workspace_path, home_path=home_path)

            await pod_mgr.create(
                env_id=env.id,
                namespace=namespace,
                image=env.image,
                environment_type=env.environment_type,
                cpu=env.cpu,
                memory=env.memory,
                gpu_count=env.gpu_count,
                env_vars=final_env_vars,
                volumes=extra_volumes or [],
                volume_mounts=extra_volume_mounts or [],
                image_pull_secret=pull_secret_name,
                node_selector={"kubeai": "true"},
            )
        except Exception as e:
            logger.error("start_server_failed", env_id=str(env.id), error=str(e))
            old_status = env.status
            env.status = DevEnvironmentStatus.FAILED
            env.error_message = f"启动失败: {e}"
            await self.db.commit()
            if old_status != env.status:
                await self._publish_status_change(env.tenant_id, env.id, old_status, env.status)
            raise

        await self.db.commit()
        await self.db.refresh(env)

    async def delete_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        """API 路径: 仅校验存在性, 由 task 负责真实删除 Pod + Service + Ingress + DB."""
        env = await self._get_environment_or_fail(env_id, tenant_id)
        return env

    async def delete_environment_async(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """真实删除 Pod + Service + Ingress + DB 记录, 由 task 调用."""
        env = await self._get_environment_or_fail(env_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        pod_mgr = get_dev_pod_manager()
        try:
            await pod_mgr.delete(env.id, namespace)
        except Exception as e:
            logger.warning("delete_dev_pod_failed", env_id=str(env.id), error=str(e))

        await self.db.delete(env)
        await self.db.commit()

    def build_access_url(self, env: DevEnvironment) -> str:
        return dev_access_url(env.id)

    def _home_path(self) -> str:
        return f"{KUBEAI_CONTAINER_ROOT}/home"

    def _workspace_path(self) -> str:
        return f"{KUBEAI_CONTAINER_ROOT}/workspace"

    def _dataset_mount_path(self, dataset_name: str, version_number: int) -> str:
        return f"{KUBEAI_CONTAINER_ROOT}/datasets/{sanitize_k8s_name(dataset_name)}/v{version_number}"

    def _make_spawner_name(self, *, username: str, user_id: uuid.UUID, env_id: uuid.UUID) -> str:
        return f"devenv-{sanitize_k8s_name(username, max_length=40)}-{str(user_id)[:8]}-{str(env_id)[:8]}"

    async def _build_volumes(
        self,
        *,
        datasets: list[DatasetMountRequest] | None,
        tenant_id: uuid.UUID,
        tenant_name: str,
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
                host_path = make_dataset_host_path(tenant_name, dataset.name, version.version_number)
                mount_path = self._dataset_mount_path(dataset.name, version.version_number)

                vol_name = f"dataset-{sanitize_k8s_name(dataset.name)}-v{version.version_number}"
                extra_volumes.append({"name": vol_name, "hostPath": {"path": host_path, "type": "DirectoryOrCreate"}})
                extra_volume_mounts.append({"name": vol_name, "mountPath": mount_path, "readOnly": True})

                mounted_datasets_info.append(
                    {
                        "dataset_id": str(dataset.id),
                        "dataset_name": dataset.name,
                        "version_id": str(version.id),
                        "version_number": version.version_number,
                        "host_path": host_path,
                        "mount_path": mount_path,
                    }
                )
        elif mounted_datasets:
            for md in mounted_datasets:
                version_number = int(md["version_number"])
                mount_path = self._dataset_mount_path(md["dataset_name"], version_number)
                md["mount_path"] = mount_path
                host_path = make_dataset_host_path(tenant_name, md["dataset_name"], version_number)
                vol_name = f"dataset-{sanitize_k8s_name(md['dataset_name'])}-v{version_number}"
                extra_volumes.append({"name": vol_name, "hostPath": {"path": host_path, "type": "DirectoryOrCreate"}})
                extra_volume_mounts.append({"name": vol_name, "mountPath": mount_path, "readOnly": True})

        return extra_volumes, extra_volume_mounts, mounted_datasets_info or None

    async def _sync_environment_status(self, env: DevEnvironment, namespace: str) -> None:
        pod_mgr = get_dev_pod_manager()
        pod_status = await pod_mgr.get_pod_status(env.id, namespace)

        if not pod_status:
            self._mark_missing_server_status(env, "Pod 不存在, 启动可能已失败")
            return

        phase = pod_status["phase"]
        ready = pod_status["ready"]

        if phase in ("Running", "Succeeded") and ready:
            new_status = DevEnvironmentStatus.RUNNING
            env.access_url = self.build_access_url(env)
            last_activity = pod_status.get("last_activity")
            env.last_active_at = last_activity or datetime.now(UTC).isoformat()
            env.error_message = None
            env.stopped_reason = None
        elif phase in ("Pending", "ContainerCreating"):
            new_status = DevEnvironmentStatus.CREATING
        elif phase == "Failed":
            new_status = DevEnvironmentStatus.FAILED
        else:
            return  # no change

        if new_status != env.status:
            old_status = env.status
            logger.info(
                "dev_environment_status_changed",
                env_id=str(env.id),
                old_status=old_status,
                new_status=new_status,
            )
            env.status = new_status
            await self._publish_status_change(env.tenant_id, env.id, old_status, new_status.value)

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
        algorithm_id: uuid.UUID | None = None,
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
            merged["HOME"] = home_path  # Ensure shell/tools use persistent home
        merged["SHELL"] = "/bin/bash"  # Explicit shell for terminal integration
        if algorithm_id:
            merged["KUBEAI_ALGORITHM_ID"] = str(algorithm_id)
        return merged

    async def _extract_algorithm_to_home(
        self,
        *,
        algorithm_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_home_host_path: str,
    ) -> None:
        """Extract algorithm zip archive into the user home host path.

        The extracted files will be available under
        ``/kubeai/home/algorithm-<algorithm_id>/`` when the dev environment
        container starts.
        """
        result = await self.db.execute(
            select(Algorithm).where(Algorithm.id == algorithm_id, Algorithm.tenant_id == tenant_id)
        )
        algo = result.scalar_one_or_none()
        if not algo:
            logger.warning("algorithm_not_found_for_dev_env", algorithm_id=str(algorithm_id))
            return

        if not algo.storage_path:
            logger.warning("algorithm_has_no_storage_path", algorithm_id=str(algorithm_id))
            return

        tenant = await self._get_tenant_or_fail(tenant_id)
        storage = AlgorithmStorageService(tenant.name)
        zip_path = storage.get_file_path(algo.user_id, algorithm_id)

        if not zip_path.exists():
            logger.warning("algorithm_zip_not_found", path=str(zip_path))
            return

        dest_dir = Path(user_home_host_path) / f"algorithm-{algorithm_id}"

        def _extract() -> None:
            dest_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                zf.extractall(str(dest_dir))
            # Ensure extracted files are readable by the container user
            for p in dest_dir.rglob("*"):
                if p.is_file():
                    p.chmod(0o644)
                elif p.is_dir():
                    p.chmod(0o755)

        await asyncio.to_thread(_extract)
        logger.info(
            "algorithm_extracted_to_home",
            algorithm_id=str(algorithm_id),
            dest=str(dest_dir),
        )

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
    async def _publish_status_change(
        tenant_id: uuid.UUID,
        env_id: uuid.UUID,
        old_status: str,
        new_status: str,
    ) -> None:
        await publish_ws_event(
            tenant_id=tenant_id,
            event="dev_environment.status_changed",
            payload={"id": str(env_id), "old_status": old_status, "new_status": new_status},
        )
