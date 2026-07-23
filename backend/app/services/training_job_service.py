from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from kubernetes_asyncio.client.exceptions import ApiException
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.core.gpu_metrics import (
    degraded_response,
    metrics_success,
    parse_duration,
    parse_gpu_history,
    parse_gpu_metrics,
)
from app.core.ws_pubsub import get_ws_pubsub
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.pod import get_pod_log, list_vcjob_pods, resolve_pod_failure_reason, stream_pod_logs
from app.integrations.k8s.pvc import (
    make_dataset_host_path,
    make_user_home_host_path,
    make_workspace_host_path,
)
from app.integrations.k8s.resource_quota import get_quota_used
from app.integrations.k8s.tensorboard import get_tensorboard_manager, tensorboard_access_url
from app.integrations.volcano.client import (
    batch_get_vcjob_phases,
    create_vcjob,
    delete_vcjob,
)
from app.integrations.volcano.job_builder import build_vcjob
from app.models.dataset import Dataset, DatasetVersion
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus, ImageCategory, TrainingJobStatus
from app.models.experiment import Experiment
from app.models.image import Image
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.models.user import User
from app.services.experiment_service import ExperimentService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.integrations.prometheus.client import PrometheusClient

logger = logging.getLogger(__name__)

ALLOWED_STOP_STATUSES = {TrainingJobStatus.RUNNING, TrainingJobStatus.QUEUED, TrainingJobStatus.PENDING}
TERMINAL_STATUSES = {TrainingJobStatus.SUCCEEDED, TrainingJobStatus.FAILED, TrainingJobStatus.STOPPED}


class TrainingJobService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_training_job_record(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        image_id: uuid.UUID,
        command: str,
        description: str | None = None,
        dataset_id: uuid.UUID | None = None,
        dataset_version_id: uuid.UUID | None = None,
        hyperparameters: list[dict[str, str]] | None = None,
        gpu_count: int = 1,
        gpu_mode: str = "exclusive",
        cpu: str = "4",
        memory: str = "8Gi",
        priority: str = "normal",
        worker_count: int = 1,
        source_experiment_id: uuid.UUID | None = None,
        source: str = "manual",
        source_env_id: uuid.UUID | None = None,
        mlflow_enabled: bool = False,
        tensorboard_enabled: bool = False,
    ) -> TrainingJob:
        """创建训练任务 DB 记录 (仅校验 + 写入, 不执行 K8s 操作).

        Volcano VCJob 提交由 Taskiq worker 异步执行.

        Args:
            mlflow_enabled: 是否为此任务启用 MLflow 实验追踪. 默认 False (不启用).
                开启后平台创建 Experiment 记录, 训练脚本收到 MLFLOW_* 环境变量.
            tensorboard_enabled: 是否注入 TensorBoard sidecar 容器. 默认 False (不注入).
                开启后 trainer 与 sidecar 共享 emptyDir 卷, trainer 写到 /kubeai/tensorboard
                的 tfevents 文件会被 TensorBoard 自动读取.
        """
        await self._get_image_or_fail(image_id)

        # Resolve dataset version
        resolved_dataset_id = dataset_id
        resolved_dataset_version_id = dataset_version_id
        if dataset_id:
            await self._get_dataset_or_fail(dataset_id, tenant_id)
            if dataset_version_id:
                await self._get_version_or_fail(dataset_version_id, dataset_id)
            else:
                version = await self._get_latest_version(dataset_id)
                resolved_dataset_version_id = version.id

        hp_dict: dict[str, str] | None = None
        if hyperparameters:
            hp_dict = {item["key"]: item["value"] for item in hyperparameters}

        final_description = description
        if source_experiment_id:
            suffix = f"（基于实验 #{source_experiment_id} 复现）"
            final_description = f"{description}{suffix}" if final_description else suffix
            source = "experiment_reproduction"

        job = TrainingJob(
            tenant_id=tenant_id,
            name=name,
            description=final_description,
            created_by=user_id,
            dataset_id=resolved_dataset_id,
            dataset_version_id=resolved_dataset_version_id,
            image_id=image_id,
            command=command,
            hyperparameters=hp_dict,
            gpu_count=gpu_count,
            gpu_mode=gpu_mode,
            cpu=cpu,
            memory=memory,
            priority=priority,
            worker_count=worker_count,
            mlflow_enabled=mlflow_enabled,
            tensorboard_enabled=tensorboard_enabled,
            status=TrainingJobStatus.PENDING,
            source=source,
            source_env_id=source_env_id,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def execute_training_job_submission(
        self,
        job_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> TrainingJob:
        """由 Taskiq worker 调用: 提交 Volcano VCJob + 创建 MLflow 实验 (若 mlflow_enabled)."""
        job = await self._get_job_or_fail(job_id, tenant_id)

        # 防止竞态: 任务在队列中积压期间被用户停止
        if job.status == TrainingJobStatus.STOPPED:
            logger.info("Job %s was stopped before submission, skipping K8s submission", job_id)
            return job

        tenant = await self._get_tenant_or_fail(tenant_id)
        user = await self._get_user_or_fail(job.created_by)
        image = await self._get_image_or_fail(job.image_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        # GPU 配额检查
        await self._check_gpu_quota(namespace, tenant.gpu_limit, job.gpu_count * job.worker_count)

        # 构建数据集挂载信息
        dataset_host_path: str | None = None
        mount_path: str | None = None
        if job.dataset_id:
            dataset = await self._get_dataset_or_fail(job.dataset_id, tenant_id)
            if job.dataset_version_id:
                version = await self._get_version_or_fail(job.dataset_version_id, job.dataset_id)
            else:
                version = await self._get_latest_version(job.dataset_id)
            dataset_host_path = make_dataset_host_path(tenant.name, dataset.name, version.version_number)
            mount_path = f"/kubeai/datasets/{dataset.name}/v{version.version_number}"

        workspace_host_path = make_workspace_host_path(tenant.name)
        user_home_host_path = make_user_home_host_path(user.username)

        vcjob_name = f"training-{sanitize_k8s_name(job.name)}"

        # MLflow 绑定是训练任务的属性, 不是平台假设.
        mlflow_tracking_uri: str | None = None
        mlflow_experiment_name: str | None = None
        mlflow_run_id: str | None = None
        if job.mlflow_enabled:
            mlflow_tracking_uri = settings.MLFLOW_TRACKING_URI
            mlflow_experiment_name = f"kubeai-{str(tenant_id)[:8]}-{sanitize_k8s_name(job.name)}"

        hp_dict = job.hyperparameters

        # MLflow Experiment + Run 创建 (如启用): 在 VCJob 构建之前完成.
        # 平台预创建 run 并把 run_id 注入容器 MLFLOW_RUN_ID, 训练脚本 resume 它形成强绑定.
        # 若 MLflow 不可用, 直接抛错 — 不构建 VCJob, 避免留下半截状态.
        if job.mlflow_enabled:
            experiment_service = ExperimentService(self.db)
            experiment = await experiment_service.create_experiment(
                tenant_id=tenant_id,
                training_job_id=job.id,
                mlflow_experiment_name=mlflow_experiment_name or "",
            )
            mlflow_run_id = experiment.mlflow_run_id

        vcjob_body = build_vcjob(
            vcjob_name=vcjob_name,
            namespace=namespace,
            image_ref=image.image_ref,
            command=job.command,
            cpu=job.cpu,
            memory=job.memory,
            gpu_count=job.gpu_count,
            gpu_mode=job.gpu_mode,
            job_id=str(job.id),
            worker_count=job.worker_count,
            hyperparameters=hp_dict,
            priority=job.priority,
            dataset_host_path=dataset_host_path,
            dataset_mount_path=mount_path,
            workspace_host_path=workspace_host_path,
            user_home_host_path=user_home_host_path,
            username=user.username,
            mlflow_tracking_uri=mlflow_tracking_uri,
            mlflow_experiment_name=mlflow_experiment_name,
            mlflow_run_id=mlflow_run_id,
            tensorboard_enabled=job.tensorboard_enabled,
        )

        try:
            await create_vcjob(namespace, vcjob_body)
        except Exception as e:
            logger.error("Failed to submit VCJob %s: %s", vcjob_name, e)
            # 持久化已 flush 的 Experiment: 重试时 create_experiment 据此幂等短路,
            # 不重复创建 MLflow run. 任务状态由 Taskiq 层 (_mark_retrying/_mark_failed) 统一管理.
            await self.db.commit()
            if isinstance(e, ApiException) and e.status == 404:
                raise ExternalServiceException("Volcano VCJob CRD 未安装, 请确认集群已部署 Volcano") from e
            raise

        # TensorBoard 可视化资源 (Service + APISIX 路由). 失败仅记录,
        # 不回滚 VCJob — 可视化是辅助功能, 不应阻塞训练.
        if job.tensorboard_enabled:
            try:
                await get_tensorboard_manager().create(job_id=job.id, namespace=namespace, vcjob_name=vcjob_name)
            except Exception as e:
                logger.warning("TensorBoard 资源创建失败 (job=%s): %s", job.id, e)

        old_status = job.status
        job.vcjob_name = vcjob_name
        job.status = TrainingJobStatus.QUEUED

        await self.db.commit()
        await self.db.refresh(job)
        self._publish_status_change(job.tenant_id, job.id, old_status, job.status)
        return job

    async def list_training_jobs(
        self,
        *,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        name: str | None = None,
    ) -> tuple[list[TrainingJob], int]:
        query = select(TrainingJob).where(TrainingJob.tenant_id == tenant_id)

        if status:
            query = query.where(TrainingJob.status == status)
        if name:
            query = query.where(TrainingJob.name.ilike(f"%{name}%"))

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(TrainingJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        jobs = list(result.scalars().all())

        non_terminal = [
            job
            for job in jobs
            if job.vcjob_name and job.status not in (TrainingJobStatus.SUCCEEDED, TrainingJobStatus.STOPPED)
        ]
        if non_terminal:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            vcjob_names = [j.vcjob_name for j in non_terminal if j.vcjob_name]
            phases = await batch_get_vcjob_phases(namespace, vcjob_names)
            modified_jobs: list[tuple[TrainingJob, str]] = []
            for job in non_terminal:
                if not job.vcjob_name:
                    continue
                phase = phases.get(job.vcjob_name)
                if phase is None:
                    logger.warning(
                        "VCJob %s not found for job %s, keeping status %s",
                        job.vcjob_name,
                        job.id,
                        job.status,
                    )
                    continue
                new_status = TrainingJobStatus(phase)
                if new_status != job.status:
                    old_status = job.status
                    job.status = new_status
                    self._update_job_timestamps(job, new_status)
                    if new_status == TrainingJobStatus.FAILED:
                        job.error_message = await self._extract_failure_reason(namespace, job.vcjob_name)
                    else:
                        job.error_message = None
                    logger.info("TrainingJob %s status synced (batch): %s -> %s", job.id, old_status, new_status)
                    if new_status in TERMINAL_STATUSES:
                        try:
                            experiment_service = ExperimentService(self.db)
                            await experiment_service.sync_experiment_status(job.id, new_status)
                        except Exception as e:
                            logger.warning("Failed to sync experiment status for job %s: %s", job.id, e)
                    modified_jobs.append((job, old_status))
            if modified_jobs:
                await self.db.commit()
                for job, old_status in modified_jobs:
                    await self.db.refresh(job)
                    self._publish_status_change(job.tenant_id, job.id, old_status, job.status)

        return jobs, total

    async def get_training_job(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> TrainingJob:
        job = await self._get_job_or_fail(job_id, tenant_id)
        await self._sync_job_status(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_training_job_record(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> TrainingJob:
        """DB-only fetch — no K8s status sync, no commit.

        Used by hot paths (e.g. APISIX forward-auth, which fires per TensorBoard
        sub-request) where a full ``get_training_job`` would hammer K8s + the DB.
        """
        return await self._get_job_or_fail(job_id, tenant_id)

    async def stop_training_job_record(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> TrainingJob:
        """标记训练任务为已停止 (仅 DB 操作, K8s 删除由 Taskiq worker 异步执行)."""
        job = await self._get_job_or_fail(job_id, tenant_id)

        if job.status not in ALLOWED_STOP_STATUSES:
            raise ConflictException(f"当前状态为 {job.status}, 无法停止任务")

        old_status = job.status
        job.status = TrainingJobStatus.STOPPED
        await self.db.commit()
        await self.db.refresh(job)
        self._publish_status_change(job.tenant_id, job.id, old_status, job.status)
        return job

    async def execute_training_job_stop(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """由 Taskiq worker 调用: 删除 K8s Volcano VCJob (best-effort).

        若作业启用了 TensorBoard 可视化, 一并清理 Service + APISIX 路由.
        若作业启用了 MLflow 追踪, 先把 run 置为 KILLED (Pod 被 SIGTERM 强杀时脚本
        来不及 end_run, 否则 run 会永远停在 RUNNING).
        """
        job = await self._get_job_or_fail(job_id, tenant_id)

        if not job.vcjob_name:
            return

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        # MLflow run 终止先于 VCJob 删除: 主动把 latest run 置 KILLED, 回填 run_id.
        if job.mlflow_enabled:
            try:
                experiment_service = ExperimentService(self.db)
                await experiment_service.terminate_experiments_for_job(job.id)
                await experiment_service.sync_experiment_status(job.id, "stopped")
                await self.db.commit()
            except Exception as e:
                logger.warning("Failed to terminate MLflow runs for job %s: %s", job.id, e)

        # TensorBoard 资源先于 VCJob 清理 (顺序无关, 都 best-effort).
        if job.tensorboard_enabled:
            try:
                await get_tensorboard_manager().delete(job.id, namespace)
            except Exception as e:
                logger.warning("TensorBoard 资源清理失败 (job=%s): %s", job.id, e)

        try:
            await delete_vcjob(namespace, job.vcjob_name)
            logger.info("Deleted VCJob %s for stopped job %s", job.vcjob_name, job.id)
        except Exception as e:
            logger.warning("Failed to delete VCJob %s: %s", job.vcjob_name, e)

    async def delete_training_job_record(
        self, job_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> tuple[str | None, str, bool, str | None]:
        """标记训练任务为已删除 (DB 操作), 返回 vcjob_name / namespace / tensorboard_enabled / mlflow_experiment_id.

        仅允许删除终态任务 (已成功/已失败/已停止).
        """
        job = await self._get_job_or_fail(job_id, tenant_id)

        if job.status not in TERMINAL_STATUSES:
            raise ConflictException(f"当前状态为 {job.status}, 仅终态任务可以删除. 请先停止任务.")

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        vcjob_name = job.vcjob_name
        tensorboard_enabled = job.tensorboard_enabled

        # 删 job 前先取 MLflow experiment_id: Experiment 记录会随 job 的 FK CASCADE 删除,
        # worker 阶段无法再查到, 须由此带出交给 worker 清理 MLflow 侧数据.
        exp_result = await self.db.execute(
            select(Experiment.mlflow_experiment_id).where(Experiment.training_job_id == job_id)
        )
        mlflow_experiment_id = exp_result.scalar_one_or_none()

        await self.db.delete(job)
        await self.db.commit()
        return vcjob_name, namespace, tensorboard_enabled, mlflow_experiment_id

    async def execute_training_job_delete(
        self,
        job_id: uuid.UUID,
        vcjob_name: str | None,
        namespace: str,
        tensorboard_enabled: bool = False,
        mlflow_experiment_id: str | None = None,
    ) -> None:
        """由 Taskiq worker 调用: 清理 K8s VCJob + TensorBoard + MLflow 资源 (best-effort).

        DB 记录已由 API 同步删除, 此处仅做外部资源清理.
        """
        # TensorBoard 资源先于 VCJob 清理 (顺序无关, 都 best-effort).
        if tensorboard_enabled:
            try:
                await get_tensorboard_manager().delete(job_id, namespace)
            except Exception as e:
                logger.warning("TensorBoard 资源清理失败 (job=%s): %s", job_id, e)

        # MLflow experiment 删除 (连带其下 run), 避免孤儿 MLflow 数据.
        if mlflow_experiment_id:
            try:
                await ExperimentService(self.db).delete_experiment(mlflow_experiment_id)
            except Exception as e:
                logger.warning("MLflow 清理失败 (job=%s, exp=%s): %s", job_id, mlflow_experiment_id, e)

        if not vcjob_name:
            return
        try:
            await delete_vcjob(namespace, vcjob_name)
            logger.info("Deleted VCJob %s for deleted training job", vcjob_name)
        except Exception as e:
            logger.warning("Failed to delete VCJob %s for deleted job: %s", vcjob_name, e)
            # Best-effort: 资源清理器最终会处理孤儿 VCJob

    async def retry_training_job(self, job_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID) -> TrainingJob:
        job = await self._get_job_or_fail(job_id, tenant_id)

        if job.status not in (TrainingJobStatus.FAILED, TrainingJobStatus.STOPPED):
            raise ConflictException(f"当前状态为 {job.status}, 仅失败或已停止的任务可以重试")

        # Best-effort 清理旧 VCJob, 避免孤儿 K8s 资源
        if job.vcjob_name:
            try:
                tenant = await self._get_tenant_or_fail(tenant_id)
                namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
                await delete_vcjob(namespace, job.vcjob_name)
                logger.info("Cleaned up old VCJob %s for retry of job %s", job.vcjob_name, job.id)
            except Exception as e:
                logger.warning("Failed to clean up old VCJob %s: %s", job.vcjob_name, e)

        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        new_name = f"{job.name}-retry-{timestamp}"

        hp_list = [{"key": k, "value": v} for k, v in job.hyperparameters.items()] if job.hyperparameters else None

        return await self.create_training_job_record(
            tenant_id=tenant_id,
            user_id=user_id,
            name=new_name,
            description=job.description,
            dataset_id=job.dataset_id,
            dataset_version_id=job.dataset_version_id,
            image_id=job.image_id,
            command=job.command,
            hyperparameters=hp_list,
            gpu_count=job.gpu_count,
            gpu_mode=job.gpu_mode,
            cpu=job.cpu,
            memory=job.memory,
            priority=job.priority,
            worker_count=job.worker_count,
            mlflow_enabled=job.mlflow_enabled,
            tensorboard_enabled=job.tensorboard_enabled,
        )

    async def create_from_environment(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        environment_id: uuid.UUID,
        name: str,
        command: str,
        description: str | None = None,
        image_id: uuid.UUID | None = None,
        dataset_id: uuid.UUID | None = None,
        dataset_version_id: uuid.UUID | None = None,
        gpu_count: int | None = None,
        gpu_mode: str = "exclusive",
        cpu: str | None = None,
        memory: str | None = None,
        priority: str = "normal",
        worker_count: int = 1,
        hyperparameters: list[dict[str, str]] | None = None,
        mlflow_enabled: bool = False,
        tensorboard_enabled: bool = False,
    ) -> TrainingJob:
        env = await self._get_environment_or_fail(environment_id, tenant_id)
        if env.status != DevEnvironmentStatus.RUNNING:
            raise BadRequestException("只能从运行中的开发环境提交训练任务")

        resolved_image_id = image_id or await self._resolve_image_from_env(env)

        resolved_dataset_id = dataset_id
        resolved_dataset_version_id = dataset_version_id
        if dataset_id is None and env.mounted_datasets:
            first = env.mounted_datasets[0]
            resolved_dataset_id = uuid.UUID(first["dataset_id"])
            resolved_dataset_version_id = uuid.UUID(first["version_id"])

        resolved_gpu = gpu_count if gpu_count is not None else env.gpu_count
        resolved_cpu = cpu or env.cpu
        resolved_memory = memory or env.memory

        return await self.create_training_job_record(
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            description=description,
            dataset_id=resolved_dataset_id,
            dataset_version_id=resolved_dataset_version_id,
            image_id=resolved_image_id,
            command=command,
            hyperparameters=hyperparameters,
            gpu_count=resolved_gpu,
            gpu_mode=gpu_mode,
            cpu=resolved_cpu,
            memory=resolved_memory,
            priority=priority,
            worker_count=worker_count,
            mlflow_enabled=mlflow_enabled,
            tensorboard_enabled=tensorboard_enabled,
            source="dev_environment",
            source_env_id=environment_id,
        )

    async def _sync_job_status(self, job: TrainingJob) -> None:
        if not job.vcjob_name:
            return

        # SUCCEEDED / STOPPED 是真正的终态. FAILED 不是——Volcano 可能已自动重试成功
        if job.status in (TrainingJobStatus.SUCCEEDED, TrainingJobStatus.STOPPED):
            return

        try:
            tenant = await self._get_tenant_or_fail(job.tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            phases = await batch_get_vcjob_phases(namespace, [job.vcjob_name])
            phase = phases.get(job.vcjob_name)

            if phase is None:
                logger.warning(
                    "VCJob %s not found for job %s, keeping status %s",
                    job.vcjob_name,
                    job.id,
                    job.status,
                )
                return

            new_status = TrainingJobStatus(phase)

            if new_status != job.status:
                old_status = job.status
                job.status = new_status
                self._update_job_timestamps(job, new_status)
                if new_status == TrainingJobStatus.FAILED:
                    job.error_message = await self._extract_failure_reason(namespace, job.vcjob_name)
                else:
                    job.error_message = None
                logger.info(
                    "TrainingJob %s status synced: %s -> %s",
                    job.id,
                    old_status,
                    new_status,
                )
                if new_status in TERMINAL_STATUSES:
                    try:
                        experiment_service = ExperimentService(self.db)
                        await experiment_service.sync_experiment_status(job.id, new_status)
                    except Exception as e:
                        logger.warning("Failed to sync experiment status for job %s: %s", job.id, e)
                    try:
                        from app.services.notification_service import NotificationService

                        await NotificationService(self.db).create_training_outcome_notification(
                            job, is_success=(new_status == TrainingJobStatus.SUCCEEDED)
                        )
                    except Exception as e:
                        logger.warning("Failed to send notification for job %s: %s", job.id, e)

                    # WebSocket push
                    self._publish_status_change(job.tenant_id, job.id, old_status, job.status)
        except Exception as e:
            logger.warning("Failed to sync VCJob status for %s: %s", job.vcjob_name, e)

    async def _extract_failure_reason(self, namespace: str, vcjob_name: str) -> str:
        return await resolve_pod_failure_reason(namespace, vcjob_name)

    @staticmethod
    def _update_job_timestamps(job: TrainingJob, new_status: TrainingJobStatus) -> None:
        if new_status == TrainingJobStatus.RUNNING and not job.started_at:
            job.started_at = datetime.now(UTC)
        elif new_status in (TrainingJobStatus.SUCCEEDED, TrainingJobStatus.FAILED, TrainingJobStatus.STOPPED):
            if not job.started_at:
                job.started_at = job.created_at
            if not job.finished_at:
                job.finished_at = datetime.now(UTC)

    @staticmethod
    def _publish_status_change(tenant_id: uuid.UUID, job_id: uuid.UUID, old_status: str, new_status: str) -> None:
        pubsub = get_ws_pubsub()
        if pubsub is None:
            return
        import asyncio

        _task = asyncio.ensure_future(  # noqa: RUF006
            pubsub.publish(
                tenant_id=tenant_id,
                event="training.status_changed",
                payload={"id": str(job_id), "old_status": old_status, "new_status": new_status},
            )
        )

    async def stream_logs(
        self,
        *,
        job_id: uuid.UUID,
        tenant_id: uuid.UUID,
        pod_name: str | None = None,
        tail_lines: int = 100,
    ) -> AsyncGenerator[str, None]:
        job = await self._get_job_or_fail(job_id, tenant_id)
        if not job.vcjob_name:
            raise BadRequestException("任务尚未提交到集群")

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        # Sync status from K8s first so we don't attempt SSE streaming against
        # a pod that already terminated (the frontend picks streaming vs
        # history based on DB status; stale "running" → broken SSE).
        await self._sync_job_status(job)
        await self.db.commit()
        await self.db.refresh(job)

        if not pod_name:
            pods = await list_vcjob_pods(namespace, job.vcjob_name)
            if not pods:
                raise NotFoundException("未找到任务关联的 Pod（任务可能已结束）")
            pod_name = pods[0]["pod_name"]

        async for line in stream_pod_logs(namespace, pod_name, tail_lines=tail_lines):
            yield line

    async def get_logs(
        self,
        *,
        job_id: uuid.UUID,
        tenant_id: uuid.UUID,
        pod_name: str | None = None,
        tail_lines: int = 1000,
    ) -> tuple[list[str], bool, int]:
        job = await self._get_job_or_fail(job_id, tenant_id)
        if not job.vcjob_name:
            raise BadRequestException("任务尚未提交到集群")

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        # Sync status from K8s first — ensures we have the latest state before
        # deciding whether to return history or stream.
        await self._sync_job_status(job)
        await self.db.commit()
        await self.db.refresh(job)

        if not pod_name:
            pods = await list_vcjob_pods(namespace, job.vcjob_name)
            if not pods:
                return [], False, 0
            pod_name = pods[0]["pod_name"]

        raw = await get_pod_log(namespace, pod_name, tail_lines=tail_lines)
        lines = raw.splitlines() if raw else []
        return lines, len(lines) >= tail_lines, len(lines)

    async def list_pods(self, *, job_id: uuid.UUID, tenant_id: uuid.UUID) -> list[dict[str, str]]:
        job = await self._get_job_or_fail(job_id, tenant_id)
        if not job.vcjob_name:
            return []
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        return await list_vcjob_pods(namespace, job.vcjob_name)

    async def get_metrics(
        self,
        *,
        job_id: uuid.UUID,
        tenant_id: uuid.UUID,
        prom_client: PrometheusClient | None,
        duration: str = "20m",
        step: str = "15s",
    ) -> dict[str, Any]:
        job = await self._get_job_or_fail(job_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        # TensorBoard 可视化入口: 启用了 TensorBoard 的作业返回 APISIX 鉴权后的 URL.
        # 仅作业处于非终态时返回, 终态后 sidecar 容器随 Pod 销毁, URL 不再可访问.
        metrics_url: str | None = None
        if job.tensorboard_enabled and job.status not in TERMINAL_STATUSES:
            metrics_url = tensorboard_access_url(job.id)

        if not prom_client:
            return degraded_response(metrics_url)

        try:
            pod_name = await self._get_running_vcjob_pod(job, namespace)

            end_ts = str(datetime.now(UTC).timestamp())
            start_ts = str((datetime.now(UTC) - parse_duration(duration)).timestamp())

            raw_metrics = await prom_client.query_gpu_metrics(namespace, pod_name)
            raw_history = await prom_client.query_gpu_utilization_range(namespace, pod_name, start_ts, end_ts, step)

            return metrics_success(
                gpu_metrics=parse_gpu_metrics(raw_metrics),
                history=parse_gpu_history(raw_history),
                metrics_url=metrics_url,
            )
        except Exception as e:
            logger.warning("Prometheus query failed, returning degraded response: %s", e)
            return degraded_response(metrics_url)

    @staticmethod
    async def _get_running_vcjob_pod(job: TrainingJob, namespace: str) -> str | None:
        """Find the first running pod name for a Volcano VCJob."""
        if not job.vcjob_name:
            return None
        try:
            pods = await list_vcjob_pods(namespace, job.vcjob_name)
            running = [p for p in pods if p["status"] == "running"]
            return running[0]["pod_name"] if running else None
        except Exception as e:
            logger.warning("Failed to list VCJob pods for metrics: %s", e)
            return None

    async def _check_gpu_quota(self, namespace: str, gpu_limit: int, requested: int) -> None:
        if requested == 0:
            return

        if gpu_limit <= 0:
            raise QuotaExceededException("租户 GPU 配额为 0, 无法创建需要 GPU 的训练任务")

        try:
            used = await get_quota_used(namespace)
            gpu_used = int(used.get("requests.nvidia.com/gpu", "0"))
        except Exception:
            gpu_used = 0

        if gpu_used + requested > gpu_limit:
            raise QuotaExceededException(
                f"GPU 配额不足: 已使用 {gpu_used} 张, 配额 {gpu_limit} 张, 请求 {requested} 张"
            )

    async def _get_job_or_fail(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> TrainingJob:
        result = await self.db.execute(
            select(TrainingJob).where(TrainingJob.id == job_id, TrainingJob.tenant_id == tenant_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundException("训练任务不存在")
        return job

    async def _get_tenant_or_fail(self, tenant_id: uuid.UUID) -> Tenant:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在")
        return tenant

    async def _get_image_or_fail(self, image_id: uuid.UUID) -> Image:
        result = await self.db.execute(select(Image).where(Image.id == image_id, Image.deleted_at.is_(None)))
        image = result.scalar_one_or_none()
        if not image:
            raise NotFoundException("镜像不存在")
        if not image.is_enabled:
            raise BadRequestException("镜像已禁用")
        if image.category != ImageCategory.TRAINING.value:
            raise BadRequestException("该镜像非训练类镜像, 不可用于训练任务")
        return image

    async def _get_user_or_fail(self, user_id: uuid.UUID) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")
        return user

    async def _get_dataset_or_fail(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> Dataset:
        result = await self.db.execute(select(Dataset).where(Dataset.id == dataset_id, Dataset.tenant_id == tenant_id))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise NotFoundException("数据集不存在")
        return dataset

    async def _get_version_or_fail(self, version_id: uuid.UUID, dataset_id: uuid.UUID) -> DatasetVersion:
        result = await self.db.execute(
            select(DatasetVersion).where(DatasetVersion.id == version_id, DatasetVersion.dataset_id == dataset_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            raise NotFoundException("数据集版本不存在")
        return version

    async def _get_latest_version(self, dataset_id: uuid.UUID) -> DatasetVersion:
        result = await self.db.execute(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.desc())
            .limit(1)
        )
        version = result.scalar_one_or_none()
        if not version:
            raise NotFoundException("数据集没有可用版本")
        return version

    async def _get_environment_or_fail(self, env_id: uuid.UUID, tenant_id: uuid.UUID) -> DevEnvironment:
        result = await self.db.execute(
            select(DevEnvironment).where(DevEnvironment.id == env_id, DevEnvironment.tenant_id == tenant_id)
        )
        env = result.scalar_one_or_none()
        if not env:
            raise NotFoundException("开发环境不存在")
        return env

    async def _resolve_image_from_env(self, env: DevEnvironment) -> uuid.UUID:
        stmt = select(Image).where(
            Image.image_ref == env.image,
            Image.deleted_at.is_(None),
            Image.is_enabled.is_(True),
            or_(Image.tenant_id == env.tenant_id, Image.tenant_id.is_(None)),
        )
        result = await self.db.execute(stmt)
        image = result.scalar_one_or_none()
        if not image:
            raise BadRequestException(
                f"开发环境的镜像 '{env.image}' 未在平台镜像仓库中注册，请通过 image_id 参数指定镜像"
            )
        return image.id

    async def sync_non_terminal_training_jobs(self, *, limit: int = 200) -> int:
        """Periodic fallback sync: reconcile all non-terminal training jobs with K8s.

        Called by the scheduled Taskiq task as a safety net behind the K8s Watch.
        Returns the number of jobs whose status was updated.
        """
        from app.integrations.volcano.client import batch_get_vcjob_phases

        stmt = (
            select(TrainingJob)
            .where(TrainingJob.vcjob_name.is_not(None))
            .where(TrainingJob.status.not_in((TrainingJobStatus.SUCCEEDED, TrainingJobStatus.STOPPED)))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        jobs = list(result.scalars().all())

        if not jobs:
            return 0

        # Group jobs by tenant for namespace resolution
        tenant_ids = {job.tenant_id for job in jobs}
        tenant_map: dict[uuid.UUID, Tenant] = {}
        for tid in tenant_ids:
            tenant_result = await self.db.execute(select(Tenant).where(Tenant.id == tid))
            t: Tenant | None = tenant_result.scalar_one_or_none()
            if t:
                tenant_map[tid] = t

        synced_count = 0
        modified_jobs: list[tuple[TrainingJob, TrainingJobStatus]] = []

        # Process per namespace
        jobs_by_ns: dict[str, list[TrainingJob]] = {}
        for job in jobs:
            tenant = tenant_map.get(job.tenant_id)
            if not tenant:
                continue
            ns = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            jobs_by_ns.setdefault(ns, []).append(job)

        for namespace, ns_jobs in jobs_by_ns.items():
            vcjob_names = [j.vcjob_name for j in ns_jobs if j.vcjob_name]
            if not vcjob_names:
                continue
            try:
                phases = await batch_get_vcjob_phases(namespace, vcjob_names)
            except Exception as exc:
                logger.warning("sync_non_terminal batch_get_vcjob_phases failed for %s: %s", namespace, exc)
                continue

            for job in ns_jobs:
                if not job.vcjob_name:
                    continue
                phase = phases.get(job.vcjob_name)
                if phase is None:
                    continue
                new_status = TrainingJobStatus(phase)
                if new_status != job.status:
                    old_status = TrainingJobStatus(job.status)
                    job.status = new_status
                    self._update_job_timestamps(job, new_status)
                    if new_status == TrainingJobStatus.FAILED:
                        with contextlib.suppress(Exception):
                            job.error_message = await self._extract_failure_reason(namespace, job.vcjob_name)
                    else:
                        job.error_message = None
                    logger.info(
                        "TrainingJob %s status synced (scheduled): %s -> %s",
                        job.id,
                        old_status,
                        new_status,
                    )
                    if new_status in TERMINAL_STATUSES:
                        try:
                            experiment_service = ExperimentService(self.db)
                            await experiment_service.sync_experiment_status(job.id, new_status)
                        except Exception as exc:
                            logger.warning("Failed to sync experiment status for job %s: %s", job.id, exc)
                        try:
                            from app.models.enums import NotificationPriority, NotificationType
                            from app.services.notification_service import NotificationService

                            notif_service = NotificationService(self.db)
                            is_success = new_status == TrainingJobStatus.SUCCEEDED
                            await notif_service.create_notification(
                                user_id=job.created_by,
                                tenant_id=job.tenant_id,
                                type=NotificationType.TRAINING_JOB,
                                title=f"训练任务{'完成' if is_success else '失败'}",
                                content=f"训练任务「{job.name}」已{'完成' if is_success else '失败'}.",
                                priority=NotificationPriority.HIGH if not is_success else NotificationPriority.MEDIUM,
                                resource_type="training_job",
                                resource_id=str(job.id),
                            )
                        except Exception as exc:
                            logger.warning("Failed to send notification for job %s: %s", job.id, exc)
                    modified_jobs.append((job, old_status))
                    synced_count += 1

        if modified_jobs:
            await self.db.commit()
            for job, old_status in modified_jobs:
                self._publish_status_change(job.tenant_id, job.id, old_status, job.status)

        return synced_count
