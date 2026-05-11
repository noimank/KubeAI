from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    QuotaExceededException,
)
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.pod import get_pod_log, list_vcjob_pods, stream_pod_logs
from app.integrations.k8s.pvc import create_pvc, make_dataset_pvc_name, pvc_exists
from app.integrations.k8s.resource_quota import get_quota_used
from app.integrations.volcano.client import (
    batch_get_vcjob_phases,
    create_vcjob,
    delete_vcjob,
)
from app.integrations.volcano.job_builder import build_vcjob
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import TrainingJobStatus
from app.models.image import Image
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.integrations.prometheus.client import PrometheusClient

logger = logging.getLogger(__name__)

ALLOWED_STOP_STATUSES = {TrainingJobStatus.RUNNING, TrainingJobStatus.QUEUED, TrainingJobStatus.PENDING}


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
    ) -> TrainingJob:
        image = await self._get_image_or_fail(image_id)

        pvc_name: str | None = None
        mount_path: str | None = None
        if dataset_id:
            dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
            if dataset_version_id:
                version = await self._get_version_or_fail(dataset_version_id, dataset_id)
            else:
                version = await self._get_latest_version(dataset_id)
                dataset_version_id = version.id
            pvc_name = make_dataset_pvc_name(dataset.name, version.version_number)
            mount_path = f"/data/datasets/{dataset.name}/v{version.version_number}"

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_count * worker_count)

        hp_dict: dict[str, str] | None = None
        if hyperparameters:
            hp_dict = {item["key"]: item["value"] for item in hyperparameters}

        job = TrainingJob(
            tenant_id=tenant_id,
            name=name,
            description=description,
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
        )
        self.db.add(job)
        await self.db.flush()

        vcjob_name = f"training-{sanitize_k8s_name(job.name)}"

        if pvc_name and not await pvc_exists(namespace, pvc_name):
            size_bytes = version.total_size_bytes or 0
            size_gb = max(1, -(-size_bytes // (1024**3)))
            await create_pvc(namespace, pvc_name, f"{size_gb}Gi")

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
            dataset_pvc_name=pvc_name,
            dataset_mount_path=mount_path,
            metrics_port=metrics_port,
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

        terminal_statuses = {TrainingJobStatus.SUCCEEDED, TrainingJobStatus.FAILED, TrainingJobStatus.STOPPED}
        non_terminal = [job for job in jobs if job.vcjob_name and job.status not in terminal_statuses]
        if non_terminal:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            vcjob_names = [j.vcjob_name for j in non_terminal if j.vcjob_name]
            phases = await batch_get_vcjob_phases(namespace, vcjob_names)
            for job in non_terminal:
                if not job.vcjob_name:
                    continue
                phase = phases.get(job.vcjob_name, "pending")
                new_status = TrainingJobStatus(phase)
                if new_status != job.status:
                    old_status = job.status
                    job.status = new_status
                    self._update_job_timestamps(job, new_status)
                    logger.info("TrainingJob %s status synced (batch): %s -> %s", job.id, old_status, new_status)
            await self.db.commit()

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

    async def _sync_job_status(self, job: TrainingJob) -> None:
        if not job.vcjob_name:
            return

        try:
            tenant = await self._get_tenant_or_fail(job.tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            phases = await batch_get_vcjob_phases(namespace, [job.vcjob_name])
            phase = phases.get(job.vcjob_name, "pending")
            new_status = TrainingJobStatus(phase)

            if new_status != job.status:
                old_status = job.status
                job.status = new_status
                self._update_job_timestamps(job, new_status)
                logger.info(
                    "TrainingJob %s status synced: %s -> %s",
                    job.id,
                    old_status,
                    new_status,
                )
        except Exception as e:
            logger.warning("Failed to sync VCJob status for %s: %s", job.vcjob_name, e)

    @staticmethod
    def _update_job_timestamps(job: TrainingJob, new_status: TrainingJobStatus) -> None:
        if new_status == TrainingJobStatus.RUNNING and not job.started_at:
            job.started_at = datetime.now(UTC)
        elif (
            new_status in (TrainingJobStatus.SUCCEEDED, TrainingJobStatus.FAILED, TrainingJobStatus.STOPPED)
            and not job.finished_at
        ):
            job.finished_at = datetime.now(UTC)

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
        if not prom_client:
            return {
                "gpu_metrics": [],
                "gpu_utilization_history": [],
                "metrics_url": metrics_url,
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
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.warning("Prometheus query failed, returning degraded response: %s", e)
            return {
                "gpu_metrics": [],
                "gpu_utilization_history": [],
                "metrics_url": metrics_url,
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
