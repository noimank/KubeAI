from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    QuotaExceededException,
)
from app.core.ws_pubsub import get_ws_pubsub
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.pod import get_pod_failure_info, get_pod_log, list_vcjob_pods, stream_pod_logs
from app.integrations.k8s.pvc import (
    make_dataset_host_path,
    make_user_home_host_path,
    make_workspace_host_path,
)
from app.integrations.k8s.resource_quota import get_quota_used
from app.integrations.volcano.client import (
    batch_get_vcjob_phases,
    create_vcjob,
    delete_vcjob,
)
from app.integrations.volcano.job_builder import build_vcjob
from app.models.dataset import Dataset, DatasetVersion
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus, TrainingJobStatus
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

    async def create_training_job(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None = None,
        dataset_id: uuid.UUID | None = None,
        dataset_version_id: uuid.UUID | None = None,
        image_id: uuid.UUID,
        command: str,
        hyperparameters: list[dict[str, str]] | None = None,
        gpu_count: int = 1,
        gpu_mode: str = "exclusive",
        cpu: str = "4",
        memory: str = "8Gi",
        priority: str = "normal",
        worker_count: int = 1,
        metrics_port: int | None = None,
        source_experiment_id: uuid.UUID | None = None,
        source: str = "manual",
        source_env_id: uuid.UUID | None = None,
    ) -> TrainingJob:
        image = await self._get_image_or_fail(image_id)

        dataset_host_path: str | None = None
        mount_path: str | None = None
        tenant = await self._get_tenant_or_fail(tenant_id)
        if dataset_id:
            dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
            if dataset_version_id:
                version = await self._get_version_or_fail(dataset_version_id, dataset_id)
            else:
                version = await self._get_latest_version(dataset_id)
                dataset_version_id = version.id
            dataset_host_path = make_dataset_host_path(tenant.name, dataset.name, version.version_number)
            mount_path = f"/data/datasets/{dataset.name}/v{version.version_number}"

        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        user = await self._get_user_or_fail(user_id)

        workspace_host_path = make_workspace_host_path(tenant.name)
        user_home_host_path = make_user_home_host_path(user.username)

        await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_count * worker_count)

        hp_dict: dict[str, str] | None = None
        if hyperparameters:
            hp_dict = {item["key"]: item["value"] for item in hyperparameters}

        final_description = description
        if source_experiment_id:
            suffix = f"（基于实验 #{source_experiment_id} 复现）"  # noqa: RUF001
            final_description = f"{description}{suffix}" if final_description else suffix
            source = "experiment_reproduction"

        job = TrainingJob(
            tenant_id=tenant_id,
            name=name,
            description=final_description,
            created_by=user_id,
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            image_id=image_id,
            command=command,
            hyperparameters=hp_dict,
            gpu_count=gpu_count,
            gpu_mode=gpu_mode,
            cpu=cpu,
            memory=memory,
            priority=priority,
            worker_count=worker_count,
            metrics_port=metrics_port,
            status=TrainingJobStatus.PENDING,
            source=source,
            source_env_id=source_env_id,
        )
        self.db.add(job)
        await self.db.flush()

        vcjob_name = f"training-{sanitize_k8s_name(job.name)}"

        mlflow_tracking_uri = settings.MLFLOW_TRACKING_URI if settings.MLFLOW_ENABLED else None
        mlflow_experiment_name = None
        mlflow_run_name = None
        if mlflow_tracking_uri:
            tenant_id_short = str(tenant_id)[:8]
            mlflow_experiment_name = f"kubeai-{tenant_id_short}-{sanitize_k8s_name(job.name)}"
            mlflow_run_name = f"job-{str(job.id)[:8]}"

        vcjob_body = build_vcjob(
            vcjob_name=vcjob_name,
            namespace=namespace,
            image_ref=image.image_ref,
            command=command,
            cpu=cpu,
            memory=memory,
            gpu_count=gpu_count,
            gpu_mode=gpu_mode,
            job_id=str(job.id),
            worker_count=worker_count,
            hyperparameters=hp_dict,
            priority=priority,
            dataset_host_path=dataset_host_path,
            dataset_mount_path=mount_path,
            workspace_host_path=workspace_host_path,
            user_home_host_path=user_home_host_path,
            username=user.username,
            metrics_port=metrics_port,
            mlflow_tracking_uri=mlflow_tracking_uri,
            mlflow_experiment_name=mlflow_experiment_name,
            mlflow_run_name=mlflow_run_name,
        )

        try:
            await create_vcjob(namespace, vcjob_body)
        except Exception as e:
            logger.error("Failed to submit VCJob %s: %s", vcjob_name, e)
            job.status = TrainingJobStatus.FAILED
            job.error_message = f"Volcano 提交失败: {e}"
            await self.db.commit()
            raise

        job.vcjob_name = vcjob_name
        job.status = TrainingJobStatus.QUEUED

        if settings.MLFLOW_ENABLED:
            try:
                experiment_service = ExperimentService(self.db)
                await experiment_service.create_experiment(
                    tenant_id=tenant_id,
                    training_job_id=job.id,
                    mlflow_experiment_name=mlflow_experiment_name,
                )
            except Exception as e:
                logger.warning("Failed to create experiment record: %s", e)

        await self.db.commit()
        await self.db.refresh(job)
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

        non_terminal = [job for job in jobs if job.vcjob_name and job.status not in TERMINAL_STATUSES]
        if non_terminal:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            vcjob_names = [j.vcjob_name for j in non_terminal if j.vcjob_name]
            phases = await batch_get_vcjob_phases(namespace, vcjob_names)
            modified_jobs: list[TrainingJob] = []
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
                    logger.info("TrainingJob %s status synced (batch): %s -> %s", job.id, old_status, new_status)
                    if new_status in TERMINAL_STATUSES:
                        try:
                            experiment_service = ExperimentService(self.db)
                            await experiment_service.sync_experiment_status(job.id, new_status)
                        except Exception as e:
                            logger.warning("Failed to sync experiment status for job %s: %s", job.id, e)
                    modified_jobs.append(job)
            if modified_jobs:
                await self.db.commit()
                for job in modified_jobs:
                    await self.db.refresh(job)
                    self._publish_status_change(job.tenant_id, job.id, job.status, job.status)

        return jobs, total

    async def get_training_job(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> TrainingJob:
        job = await self._get_job_or_fail(job_id, tenant_id)
        await self._sync_job_status(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def stop_training_job(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> TrainingJob:
        job = await self._get_job_or_fail(job_id, tenant_id)

        if job.status not in ALLOWED_STOP_STATUSES:
            raise ConflictException(f"当前状态为 {job.status}, 无法停止任务")

        if job.vcjob_name:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            try:
                await delete_vcjob(namespace, job.vcjob_name)
            except Exception as e:
                logger.warning("Failed to delete VCJob %s: %s", job.vcjob_name, e)

        job.status = TrainingJobStatus.STOPPED
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def retry_training_job(self, job_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID) -> TrainingJob:
        job = await self._get_job_or_fail(job_id, tenant_id)

        if job.status not in (TrainingJobStatus.FAILED, TrainingJobStatus.STOPPED):
            raise ConflictException(f"当前状态为 {job.status}, 仅失败或已停止的任务可以重试")

        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        new_name = f"{job.name}-retry-{timestamp}"

        return await self.create_training_job(
            tenant_id=tenant_id,
            user_id=user_id,
            name=new_name,
            description=job.description,
            dataset_id=job.dataset_id,
            dataset_version_id=job.dataset_version_id,
            image_id=job.image_id,
            command=job.command,
            hyperparameters=[{"key": k, "value": v} for k, v in job.hyperparameters.items()]
            if job.hyperparameters
            else None,
            gpu_count=job.gpu_count,
            gpu_mode=job.gpu_mode,
            cpu=job.cpu,
            memory=job.memory,
            priority=job.priority,
            worker_count=job.worker_count,
            metrics_port=job.metrics_port,
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
        metrics_port: int | None = None,
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

        return await self.create_training_job(
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
            metrics_port=metrics_port,
            source="dev_environment",
            source_env_id=environment_id,
        )

    async def _sync_job_status(self, job: TrainingJob) -> None:
        if not job.vcjob_name:
            return

        if job.status in TERMINAL_STATUSES:
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
                    except Exception as e:
                        logger.warning("Failed to send notification for job %s: %s", job.id, e)

                    # WebSocket push
                    self._publish_status_change(job.tenant_id, job.id, old_status, new_status.value)
        except Exception as e:
            logger.warning("Failed to sync VCJob status for %s: %s", job.vcjob_name, e)

    async def _extract_failure_reason(self, namespace: str, vcjob_name: str) -> str:
        try:
            pods = await list_vcjob_pods(namespace, vcjob_name)
        except Exception:
            return "训练任务已失败，但失败详情不可用（无法查询 Pod 信息）。"  # noqa: RUF001

        if not pods:
            return "训练任务已失败，但失败详情不可用（任务资源已被清理）。"  # noqa: RUF001

        for pod_info in pods:
            failure = await get_pod_failure_info(namespace, pod_info["pod_name"])
            if failure:
                return self._map_failure_message(failure)

        return "训练任务已失败，但未能获取具体失败原因。"  # noqa: RUF001

    @staticmethod
    def _map_failure_message(failure: dict[str, Any]) -> str:
        reason = failure.get("reason", "")
        exit_code = failure.get("exit_code", -1)

        if reason == "OOMKilled":
            return "内存不足 (OOM)：训练容器因超出内存限制被终止。建议增加内存配置或优化训练脚本。"  # noqa: RUF001
        if reason in ("ImagePullBackOff", "ErrImagePull"):
            return "镜像拉取失败：请检查镜像地址是否正确，以及是否具有拉取权限。"  # noqa: RUF001
        if reason == "ContainerCannotRun":
            return "容器启动失败：请检查镜像和启动命令是否正确。"  # noqa: RUF001
        if exit_code == 137:
            return "进程被终止 (SIGKILL)：可能是内存不足。建议增加内存或检查训练脚本。"  # noqa: RUF001
        if exit_code == 1:
            return "训练脚本执行错误：请查看日志获取详细错误信息。"  # noqa: RUF001
        if exit_code != 0:
            return f"训练异常退出 (退出码: {exit_code})：请查看日志获取详细信息。"  # noqa: RUF001
        return f"训练任务失败 (原因: {reason})：请查看日志获取详细信息。"  # noqa: RUF001

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

        if not pod_name:
            pods = await list_vcjob_pods(namespace, job.vcjob_name)
            if not pods:
                raise NotFoundException("未找到任务关联的 Pod")
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

        # Build metrics_url
        metrics_url: str | None = None
        if job.metrics_port and job.vcjob_name:
            try:
                pods = await list_vcjob_pods(namespace, job.vcjob_name)
                running_pods = [p for p in pods if p["status"] == "running"]
                if running_pods:
                    from kubernetes_asyncio import client as k8s_client

                    from app.integrations.k8s.client import get_k8s_clients

                    clients = await get_k8s_clients()
                    core_v1 = k8s_client.CoreV1Api(clients["api_client"])
                    pod_obj = await core_v1.read_namespaced_pod(running_pods[0]["pod_name"], namespace)
                    if pod_obj.status and pod_obj.status.pod_ip:
                        metrics_url = f"http://{pod_obj.status.pod_ip}:{job.metrics_port}"
            except Exception as e:
                logger.warning("Failed to get pod IP for metrics_url: %s", e)

        # Degraded response when Prometheus unavailable
        prometheus_available = prom_client is not None
        if not prom_client:
            return {
                "gpu_metrics": [],
                "gpu_utilization_history": [],
                "metrics_url": metrics_url,
                "prometheus_available": prometheus_available,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        try:
            # Find running pod for GPU metrics query
            pod_name: str | None = None
            if job.vcjob_name:
                pods = await list_vcjob_pods(namespace, job.vcjob_name)
                running_pods = [p for p in pods if p["status"] == "running"]
                if running_pods:
                    pod_name = running_pods[0]["pod_name"]

            # Query instant GPU metrics
            raw_metrics = await prom_client.query_gpu_metrics(namespace, pod_name)
            gpu_metrics = self._parse_gpu_metrics(raw_metrics)

            # Query GPU utilization history
            end_ts = str(datetime.now(UTC).timestamp())
            start_dt = datetime.now(UTC) - self._parse_duration(duration)
            start_ts = str(start_dt.timestamp())
            raw_history = await prom_client.query_gpu_utilization_range(namespace, pod_name, start_ts, end_ts, step)
            history = self._parse_gpu_history(raw_history)

            return {
                "gpu_metrics": gpu_metrics,
                "gpu_utilization_history": history,
                "metrics_url": metrics_url,
                "prometheus_available": prometheus_available,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.warning("Prometheus query failed, returning degraded response: %s", e)
            return {
                "gpu_metrics": [],
                "gpu_utilization_history": [],
                "metrics_url": metrics_url,
                "prometheus_available": prometheus_available,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    @staticmethod
    def _parse_gpu_metrics(raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse Prometheus instant query results into GPU metric dicts."""
        gpu_data: dict[int, dict[str, float]] = {}
        for item in raw_results:
            metric = item.get("metric", {})
            gpu_idx = int(metric.get("gpu", "0"))
            name = metric.get("__name__", "")
            value = float(item.get("value", [0, "0"])[1])

            if gpu_idx not in gpu_data:
                gpu_data[gpu_idx] = {}
            gpu_data[gpu_idx][name] = value

        points: list[dict[str, Any]] = []
        for idx in sorted(gpu_data.keys()):
            d = gpu_data[idx]
            fb_used = d.get("DCGM_FI_DEV_FB_USED", 0)
            fb_free = d.get("DCGM_FI_DEV_FB_FREE", 0)
            total_mem = fb_used + fb_free
            points.append(
                {
                    "gpu_index": idx,
                    "utilization_percent": d.get("DCGM_FI_DEV_GPU_UTIL", 0),
                    "memory_used_mib": fb_used,
                    "memory_total_mib": total_mem,
                    "temperature_c": d.get("DCGM_FI_DEV_GPU_TEMP", 0),
                    "power_w": d.get("DCGM_FI_DEV_POWER_USAGE", 0),
                }
            )
        return points

    @staticmethod
    def _parse_gpu_history(raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse Prometheus range query results into time series dicts."""
        points: list[dict[str, Any]] = []
        for series in raw_results:
            metric = series.get("metric", {})
            label = f"GPU {metric.get('gpu', '?')}"
            for ts, val in series.get("values", []):
                dt = datetime.fromtimestamp(float(ts), tz=UTC)
                points.append(
                    {
                        "timestamp": dt.isoformat(),
                        "value": float(val),
                        "label": label,
                    }
                )
        return points

    @staticmethod
    def _parse_duration(duration: str) -> timedelta:
        """Parse duration string (e.g. '20m', '1h') into timedelta."""
        from datetime import timedelta

        try:
            unit = duration[-1]
            value = int(duration[:-1])
        except (IndexError, ValueError):
            return timedelta(minutes=20)
        if unit == "s":
            return timedelta(seconds=value)
        if unit == "m":
            return timedelta(minutes=value)
        if unit == "h":
            return timedelta(hours=value)
        return timedelta(minutes=20)

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
                f"开发环境的镜像 '{env.image}' 未在平台镜像仓库中注册，请通过 image_id 参数指定镜像"  # noqa: RUF001
            )
        return image.id
