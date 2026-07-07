from __future__ import annotations

import asyncio
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    AppException,
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.core.ws_pubsub import publish_status_changed
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.dev_pod import dev_access_url, get_dev_pod_manager
from app.integrations.k8s.kubeai_volumes import (
    build_kubeai_env_vars,
    build_kubeai_volumes,
    dataset_mount_path,
)
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.network_policy import create_tenant_network_policy
from app.integrations.k8s.pvc import (
    make_dataset_host_path,
    make_user_home_host_path,
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


class DevEnvironmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Lifecycle: create / start / stop / delete (API entrypoints)
    # ------------------------------------------------------------------

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
        """Persist the environment record. Provisioning is delegated to a taskiq task."""
        dev_image = await self._get_dev_environment_image(environment_image_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if gpu_count > 0:
            await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_count)

        mounted_datasets_info = await self._resolve_mounted_datasets(
            datasets=datasets, tenant_id=tenant_id, tenant_name=tenant.name
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
            mounted_datasets=mounted_datasets_info,
            environment_image_id=dev_image.id,
            environment_type=dev_image.environment_type,
        )
        self.db.add(env)
        try:
            await self.db.commit()
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"开发环境名称「{name}」已存在") from e
        await self.db.refresh(env)
        return env

    async def start_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        """API path: validate state, mark STARTING. Actual pod start is done by the task."""
        env = await self._get_environment_or_fail(env_id, tenant_id)
        if env.status != DevEnvironmentStatus.STOPPED:
            raise ConflictException(f"当前状态为 {env.status}, 只有已停止的环境才能启动")
        await self._transition(env, DevEnvironmentStatus.STARTING)
        return env

    async def start_environment_async(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Create the dev pod and return — the K8s Pod Watcher handles RUNNING/FAILED.

        The global Pod Watcher (``dev_pod_watcher.py``) receives ADDED / MODIFIED
        events and transitions STARTING → RUNNING or FAILED with sub-second latency.

        If the pod already exists and is Ready (e.g. env was stopped in DB but pod
        survives on the node), skip creation and recover the DB state to RUNNING.
        """
        env = await self._get_environment_or_fail(env_id, tenant_id)
        if env.status != DevEnvironmentStatus.STARTING:
            logger.info("skip_dev_environment_start", env_id=str(env.id), status=env.status)
            return

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        user = await self._get_user_or_fail(env.created_by)

        # Recovery: if the pod is already Running and Ready, skip creation and
        # restore the DB state in-place.  This handles the case where a pod
        # survives a transient readiness loss that the watcher misinterpreted
        # as a crash (RUNNING → STOPPED), as well as a failed stop_server that
        # left the pod running.
        pod_mgr = get_dev_pod_manager()
        existing = await pod_mgr.get_pod(env.id, namespace)
        if existing is not None and _pod_is_running_ready(existing):
            now = datetime.now(UTC).isoformat()
            env.access_url = dev_access_url(env.id)
            env.last_active_at = env.last_active_at or now
            await self._transition(env, DevEnvironmentStatus.RUNNING, clear_error=True)
            logger.info("dev_env_recovered_from_stopped", env_id=str(env.id), name=env.name)
            return

        await self._create_dev_pod(env, tenant, user.username, namespace)

    async def stop_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        """API path: validate state, mark STOPPING. Actual pod stop is done by the task."""
        env = await self._get_environment_or_fail(env_id, tenant_id)
        if env.status not in (
            DevEnvironmentStatus.RUNNING,
            DevEnvironmentStatus.STARTING,
            DevEnvironmentStatus.STOPPING,
        ):
            raise ConflictException(f"当前状态为 {env.status}, 无法停止环境")
        await self._transition(env, DevEnvironmentStatus.STOPPING, stopped_reason="manual", clear_error=True)
        return env

    async def stop_environment_async(
        self, env_id: uuid.UUID, tenant_id: uuid.UUID, *, stopped_reason: str = "manual"
    ) -> None:
        """Delete the dev pod and rely on the K8s Pod Watcher to transition to STOPPED.

        The watcher (``dev_pod_watcher.py``) receives the DELETED event and
        moves the env from STOPPING → STOPPED.  We do NOT poll for pod
        deletion here — the watcher is the single source of truth for pod
        lifecycle events.
        """
        env = await self._get_environment_or_fail(env_id, tenant_id)
        if env.status != DevEnvironmentStatus.STOPPING:
            logger.info("skip_dev_environment_stop", env_id=str(env.id), status=env.status)
            return

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        pod_mgr = get_dev_pod_manager()
        try:
            await pod_mgr.stop_server(env.id, namespace)
        except Exception as e:
            logger.warning("stop_server_failed", env_id=str(env.id), error=str(e))
            # K8s API call failed — the pod may still be running.  The user can
            # retry (STOPPING is valid input for stop), and the idle checker will
            # also attempt to stop the pod when the timeout fires.
            return

    async def delete_environment(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        """API path: existence check only. Actual deletion is done by the task."""
        return await self._get_environment_or_fail(env_id, tenant_id)

    async def delete_environment_async(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Real deletion (pod + service + APISIX route + DB row), invoked by a taskiq worker."""
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

    # ------------------------------------------------------------------
    # Provisioning (first-time start, runs algorithm extraction too)
    # ------------------------------------------------------------------

    async def provision_environment(
        self,
        env_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        algorithm_id: uuid.UUID | None = None,
    ) -> DevEnvironment:
        """First-time provisioning: transition PENDING → STARTING and create the pod.

        After the pod is created, the K8s Pod Watcher handles the STARTING →
        RUNNING/FAILED transition via Watch events.
        """
        env = await self._get_environment_or_fail(env_id, tenant_id)
        if env.status != DevEnvironmentStatus.PENDING:
            logger.info("skip_dev_environment_provision", env_id=str(env.id), status=env.status)
            return env

        tenant = await self._get_tenant_or_fail(tenant_id)
        user = await self._get_user_or_fail(env.created_by)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        await self._transition(env, DevEnvironmentStatus.STARTING, clear_error=True)

        if algorithm_id:
            user_home_host_path = make_user_home_host_path(user.username)
            await self._extract_algorithm_to_home(
                algorithm_id=algorithm_id,
                tenant_id=env.tenant_id,
                user_home_host_path=user_home_host_path,
            )

        await self._create_dev_pod(env, tenant, user.username, namespace)
        return env

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

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
        """DB-only list query. Status transitions are driven by the K8s Pod Watcher."""
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
        """DB-only detail query. Status sync is handled by sync_dev_environment_statuses_task."""
        return await self._get_environment_or_fail(env_id, tenant_id)

    def build_access_url(self, env: DevEnvironment) -> str:
        return dev_access_url(env.id)

    # ------------------------------------------------------------------
    # Internal: pod creation
    # ------------------------------------------------------------------

    async def _create_dev_pod(
        self,
        env: DevEnvironment,
        tenant: Tenant,
        username: str,
        namespace: str,
    ) -> None:
        """Create the dev pod (Service + Pod + APISIX route).

        After the pod is submitted to K8s this method returns — the global
        Pod Watcher (``dev_pod_watcher.py``) receives ADDED / MODIFIED events
        and transitions the env from STARTING to RUNNING or FAILED.
        """
        if env.gpu_count > 0:
            await self._check_gpu_quota(namespace, tenant.gpu_limit, env.gpu_count)

        volumes, volume_mounts = self._rebuild_volumes_from_mounted(
            username=username,
            tenant_name=tenant.name,
            mounted_datasets=env.mounted_datasets,
        )

        pod_mgr = get_dev_pod_manager()
        try:
            await create_tenant_network_policy(namespace)
            pull_secret_name = await ensure_registry_pull_secret(namespace)
            final_env_vars = self._build_env_vars(env)

            await pod_mgr.create(
                env_id=env.id,
                namespace=namespace,
                image=env.image,
                environment_type=env.environment_type,
                cpu=env.cpu,
                memory=env.memory,
                gpu_count=env.gpu_count,
                env_vars=final_env_vars,
                volumes=volumes,
                volume_mounts=volume_mounts,
                image_pull_secret=pull_secret_name,
                node_selector={"kubeai": "true"},
            )
        except Exception as e:
            classified = self._classify_start_error(e)
            logger.error("start_server_failed", env_id=str(env.id), error=str(e))
            await self._transition(env, DevEnvironmentStatus.FAILED, error_message=str(classified.message))
            raise classified from e

    # ------------------------------------------------------------------
    # Internal: status transitions
    # ------------------------------------------------------------------

    async def _transition(
        self,
        env: DevEnvironment,
        new_status: DevEnvironmentStatus,
        *,
        error_message: str | None = None,
        stopped_reason: str | None = None,
        clear_error: bool = False,
    ) -> None:
        """Transition env to ``new_status`` and publish a WS event if changed."""
        old_status = env.status
        env.status = new_status
        env.error_message = None if clear_error else error_message
        if stopped_reason is not None:
            env.stopped_reason = stopped_reason
        await self.db.commit()
        await self.db.refresh(env)
        await publish_status_changed(env.tenant_id, env.id, str(old_status), str(new_status), name=env.name)

    # ------------------------------------------------------------------
    # Internal: paths & volumes
    # ------------------------------------------------------------------

    async def _resolve_mounted_datasets(
        self,
        *,
        datasets: list[DatasetMountRequest] | None,
        tenant_id: uuid.UUID,
        tenant_name: str,
    ) -> list[dict[str, Any]] | None:
        """Resolve dataset mount requests into persisted metadata."""
        if not datasets:
            return None

        info: list[dict[str, Any]] = []
        for dm in datasets:
            dataset, version = await self._resolve_dataset_mount(dm.dataset_id, dm.version_id, tenant_id)
            info.append(
                {
                    "dataset_id": str(dataset.id),
                    "dataset_name": dataset.name,
                    "version_id": str(version.id),
                    "version_number": version.version_number,
                    "host_path": make_dataset_host_path(tenant_name, dataset.name, version.version_number),
                    "mount_path": dataset_mount_path(dataset.name, version.version_number),
                }
            )
        return info or None

    def _rebuild_volumes_from_mounted(
        self,
        *,
        username: str,
        tenant_name: str,
        mounted_datasets: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Rebuild K8s volumes/mounts from persisted mounted_datasets metadata."""
        # home/workspace 卷走共享函数 (与推理服务同源); 数据集卷为 dev 独有, 自行 append.
        volumes, mounts = build_kubeai_volumes(username=username, tenant_name=tenant_name)

        for md in mounted_datasets or []:
            version_number = int(md["version_number"])
            dataset_name = md["dataset_name"]
            host_path = make_dataset_host_path(tenant_name, dataset_name, version_number)
            vol_name = f"dataset-{sanitize_k8s_name(dataset_name)}-v{version_number}"
            volumes.append({"name": vol_name, "hostPath": {"path": host_path, "type": "DirectoryOrCreate"}})
            mounts.append(
                {
                    "name": vol_name,
                    "mountPath": dataset_mount_path(dataset_name, version_number),
                    "readOnly": True,
                }
            )

        return volumes, mounts

    # ------------------------------------------------------------------
    # Internal: env vars
    # ------------------------------------------------------------------

    def _build_env_vars(
        self,
        env: DevEnvironment,
    ) -> dict[str, str]:
        # 共享 env 构建器; KUBEAI_* / HOME / SHELL 框架键优先于 env.env_vars.
        return build_kubeai_env_vars(env_id=str(env.id), extra=env.env_vars)

    # ------------------------------------------------------------------
    # Internal: algorithm extraction
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Internal: error classification
    # ------------------------------------------------------------------

    def _classify_start_error(self, exc: Exception) -> AppException:
        """Classify a pod-start failure into the most specific AppException.

        K8s ResourceQuota enforcement rejects over-quota pods with a 403
        ``Forbidden: exceeded quota`` — surface that as QuotaExceededException
        so the frontend can show a targeted message instead of a generic failure.
        """
        message = str(exc)
        lowered = message.lower()
        if "quota" in lowered and ("exceed" in lowered or "forbidden" in lowered):
            return QuotaExceededException(f"资源配额不足: {message}")
        return ExternalServiceException(f"启动失败: {message}")

    # ------------------------------------------------------------------
    # Internal: lookups
    # ------------------------------------------------------------------

    async def _get_dev_environment_image(self, image_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironmentImage:
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


# ------------------------------------------------------------------
# Module-level helpers (shared with dev_pod_watcher.py)
# ------------------------------------------------------------------


def _pod_is_running_ready(pod: object) -> bool:
    """Check whether a K8s Pod is Running, Ready, and NOT terminating."""
    from kubernetes_asyncio.client import V1Pod

    if not isinstance(pod, V1Pod):
        return False

    if pod.metadata and pod.metadata.deletion_timestamp is not None:
        return False
    if not pod.status:
        return False

    phase: str | None = pod.status.phase
    conditions = pod.status.conditions or []

    ready = any(c.type == "Ready" and c.status == "True" for c in conditions)
    return bool(phase == "Running" and ready)
