from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.core.security import generate_api_token, hash_api_token
from app.core.ws_pubsub import get_ws_pubsub
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.resource_quota import get_quota_used
from app.integrations.keda.builder import build_scaled_object
from app.integrations.keda.client import (
    create_scaled_object,
    delete_scaled_object,
    patch_scaled_object,
)
from app.integrations.kserve.builder import build_inferenceservice, build_resource_spec
from app.integrations.kserve.canary import build_canary_inferenceservice
from app.integrations.kserve.client import (
    create_inferenceservice,
    delete_inferenceservice,
    get_inferenceservice,
    patch_inferenceservice,
)
from app.models.enums import InferenceServiceStatus
from app.models.inference_service import InferenceService
from app.models.registered_model import ModelVersion, RegisteredModel
from app.models.tenant import Tenant

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.inference_service import (
        AutoScalingConfig,
        AutoScalingUpdateRequest,
        CanaryStartRequest,
        CanaryTrafficUpdateRequest,
    )

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {InferenceServiceStatus.FAILED, InferenceServiceStatus.STOPPED}
NON_TERMINAL_STATUSES = {
    InferenceServiceStatus.PENDING,
    InferenceServiceStatus.DEPLOYING,
    InferenceServiceStatus.RUNNING,
}

KEDA_SCALER_SUFFIX = "-autoscaler"


class InferenceServiceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_inference_service(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        model_version_id: uuid.UUID,
        gpu_count: int = 0,
        cpu: str = "2",
        memory: str = "4Gi",
        replicas: int = 1,
        image: str | None = None,
        env_vars: dict[str, str] | None = None,
        description: str | None = None,
        auto_scaling: AutoScalingConfig | None = None,
    ) -> tuple[InferenceService, str]:
        model_version = await self._get_model_version_or_fail(model_version_id)

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        is_auto = auto_scaling is not None and auto_scaling.scaling_mode == "auto"
        min_rep = auto_scaling.min_replicas if auto_scaling is not None and is_auto else replicas
        max_rep = auto_scaling.max_replicas if auto_scaling is not None and is_auto else replicas
        gpu_needed = gpu_count * max_rep if is_auto else gpu_count * replicas
        await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_needed)

        api_token = generate_api_token()

        svc_kwargs: dict[str, Any] = dict(
            tenant_id=tenant_id,
            created_by=user_id,
            name=name,
            model_version_id=model_version_id,
            image=image,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            replicas=replicas,
            min_replicas=min_rep,
            max_replicas=max_rep,
            scaling_mode="auto" if is_auto else "fixed",
            status=InferenceServiceStatus.PENDING,
            description=description,
            env_vars=env_vars,
            auth_token_hash=hash_api_token(api_token),
        )
        if is_auto and auto_scaling is not None:
            svc_kwargs["target_metric_type"] = auto_scaling.target_metric_type
            svc_kwargs["target_metric_value"] = auto_scaling.target_metric_value
            svc_kwargs["cooldown_period"] = auto_scaling.cooldown_period
            svc_kwargs["polling_interval"] = auto_scaling.polling_interval

        svc = InferenceService(**svc_kwargs)
        self.db.add(svc)
        await self.db.flush()

        kserve_name = f"inference-{sanitize_k8s_name(name)}"
        storage_uri = f"s3://{settings.MINIO_BUCKET_PREFIX.rstrip('-')}-models/{model_version.storage_path}"
        resources = build_resource_spec(cpu, memory, gpu_count)

        body = build_inferenceservice(
            name=kserve_name,
            namespace=namespace,
            storage_uri=storage_uri,
            resources=resources,
            replicas=replicas,
            min_replicas=min_rep,
            max_replicas=max_rep,
            env_vars=env_vars,
        )

        try:
            await create_inferenceservice(namespace, body)
        except Exception as e:
            error_msg = str(e)
            if (
                "404" in error_msg
                or "NotFound" in error_msg
                or "the server could not find the requested resource" in error_msg
            ):
                svc.status = InferenceServiceStatus.FAILED
                svc.error_message = "推理服务组件未安装"
                await self.db.commit()
                raise ExternalServiceException("推理服务组件未安装") from e
            logger.error("Failed to create InferenceService %s: %s", kserve_name, e)
            svc.status = InferenceServiceStatus.FAILED
            await self.db.commit()
            raise

        if is_auto and auto_scaling is not None:
            try:
                deploy_name = f"{kserve_name}-predictor"
                scaled_obj = build_scaled_object(
                    name=f"{kserve_name}{KEDA_SCALER_SUFFIX}",
                    namespace=namespace,
                    deploy_name=deploy_name,
                    min_replicas=min_rep,
                    max_replicas=max_rep,
                    metric_type=auto_scaling.target_metric_type,  # type: ignore[arg-type]
                    metric_value=auto_scaling.target_metric_value,  # type: ignore[arg-type]
                    cooldown_period=auto_scaling.cooldown_period,
                    polling_interval=auto_scaling.polling_interval,
                )
                await create_scaled_object(namespace, scaled_obj)
            except Exception as e:
                logger.error("Failed to create ScaledObject for %s: %s", kserve_name, e)
                try:
                    await delete_inferenceservice(namespace, kserve_name)
                except Exception:
                    logger.debug("Cleanup: InferenceService %s deletion failed after ScaledObject error", kserve_name)
                svc.status = InferenceServiceStatus.FAILED
                svc.error_message = f"自动伸缩配置失败: {e}"
                await self.db.commit()
                raise ExternalServiceException(f"KEDA 自动伸缩配置失败, 请确认集群已安装 KEDA: {e}") from e

        svc.kserve_name = kserve_name
        svc.status = InferenceServiceStatus.DEPLOYING
        await self.db.commit()
        await self.db.refresh(svc)
        return svc, api_token

    async def update_auto_scaling(
        self,
        service_id: uuid.UUID,
        tenant_id: uuid.UUID,
        config: AutoScalingUpdateRequest,
    ) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.status == InferenceServiceStatus.FAILED:
            raise ConflictException("服务处于异常状态, 请先修复后再调整伸缩配置")

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        old_mode = svc.scaling_mode
        new_mode = config.scaling_mode

        if new_mode == "auto":
            gpu_needed = svc.gpu_count * config.max_replicas
            await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_needed)

        if old_mode == "auto" and new_mode == "fixed":
            # auto → fixed: 删除 ScaledObject, KServe min=max=当前副本
            if svc.kserve_name:
                try:
                    await delete_scaled_object(namespace, f"{svc.kserve_name}{KEDA_SCALER_SUFFIX}")
                except Exception as e:
                    logger.warning("Failed to delete ScaledObject for %s: %s", svc.kserve_name, e)

            target_rep = svc.replicas if svc.replicas > 0 else 1
            if svc.kserve_name:
                await patch_inferenceservice(
                    namespace,
                    svc.kserve_name,
                    {"spec": {"predictor": {"minReplicas": target_rep, "maxReplicas": target_rep}}},
                )
            svc.min_replicas = target_rep
            svc.max_replicas = target_rep
            svc.scaling_mode = "fixed"
            svc.target_metric_type = None
            svc.target_metric_value = None

        elif new_mode == "auto" and old_mode == "fixed":
            # fixed → auto: 创建 ScaledObject, KServe min/max 为配置范围
            deploy_name = f"{svc.kserve_name}-predictor" if svc.kserve_name else ""
            scaled_obj = build_scaled_object(
                name=f"{svc.kserve_name}{KEDA_SCALER_SUFFIX}",
                namespace=namespace,
                deploy_name=deploy_name,
                min_replicas=config.min_replicas,
                max_replicas=config.max_replicas,
                metric_type=config.target_metric_type,  # type: ignore[arg-type]
                metric_value=config.target_metric_value,  # type: ignore[arg-type]
                cooldown_period=config.cooldown_period,
                polling_interval=config.polling_interval,
            )
            try:
                await create_scaled_object(namespace, scaled_obj)
            except Exception as e:
                raise ExternalServiceException(f"KEDA 自动伸缩配置失败: {e}") from e

            if svc.kserve_name:
                await patch_inferenceservice(
                    namespace,
                    svc.kserve_name,
                    {"spec": {"predictor": {"minReplicas": config.min_replicas, "maxReplicas": config.max_replicas}}},
                )
            svc.scaling_mode = "auto"
            svc.min_replicas = config.min_replicas
            svc.max_replicas = config.max_replicas
            svc.target_metric_type = config.target_metric_type
            svc.target_metric_value = config.target_metric_value
            svc.cooldown_period = config.cooldown_period
            svc.polling_interval = config.polling_interval

        elif new_mode == "auto" and old_mode == "auto":
            # auto → auto: 更新 ScaledObject, 更新 KServe min/max
            scaled_obj_body = {
                "spec": {
                    "minReplicaCount": config.min_replicas,
                    "maxReplicaCount": config.max_replicas,
                    "cooldownPeriod": config.cooldown_period,
                    "pollingInterval": config.polling_interval,
                    "triggers": build_scaled_object(
                        name="",
                        namespace="",
                        deploy_name="",
                        min_replicas=config.min_replicas,
                        max_replicas=config.max_replicas,
                        metric_type=config.target_metric_type,  # type: ignore[arg-type]
                        metric_value=config.target_metric_value,  # type: ignore[arg-type]
                        cooldown_period=config.cooldown_period,
                        polling_interval=config.polling_interval,
                    )["spec"]["triggers"],
                }
            }
            try:
                await patch_scaled_object(namespace, f"{svc.kserve_name}{KEDA_SCALER_SUFFIX}", scaled_obj_body)
            except Exception as e:
                raise ExternalServiceException(f"KEDA 伸缩配置更新失败: {e}") from e

            if svc.kserve_name:
                await patch_inferenceservice(
                    namespace,
                    svc.kserve_name,
                    {"spec": {"predictor": {"minReplicas": config.min_replicas, "maxReplicas": config.max_replicas}}},
                )
            svc.min_replicas = config.min_replicas
            svc.max_replicas = config.max_replicas
            svc.target_metric_type = config.target_metric_type
            svc.target_metric_value = config.target_metric_value
            svc.cooldown_period = config.cooldown_period
            svc.polling_interval = config.polling_interval

        # Sync canary scaling if active
        await self._sync_canary_scaling(svc, namespace, config)

        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def regenerate_token(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
        svc = await self._get_service_or_fail(service_id, tenant_id)
        new_token = generate_api_token()
        svc.auth_token_hash = hash_api_token(new_token)
        await self.db.commit()
        return new_token

    # ── Canary methods ──────────────────────────────────────────────────────

    async def start_canary(
        self,
        service_id: uuid.UUID,
        tenant_id: uuid.UUID,
        request: CanaryStartRequest,
    ) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.status != InferenceServiceStatus.RUNNING:
            raise ConflictException("服务必须处于运行状态才能启动金丝雀")
        if svc.canary_status != "none":
            raise ConflictException("该服务已有活跃的金丝雀版本")

        canary_mv = await self._get_model_version_or_fail(request.canary_model_version_id)
        rm = await self.db.get(RegisteredModel, canary_mv.registered_model_id)
        if not rm or rm.tenant_id != tenant_id:
            raise NotFoundException("金丝雀模型版本不存在")
        if canary_mv.status != "available":
            raise ConflictException("金丝雀模型版本未就绪")

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        canary_gpu = svc.gpu_count * svc.replicas
        await self._check_gpu_quota(namespace, tenant.gpu_limit, canary_gpu)

        assert svc.kserve_name is not None
        stable_kserve = await get_inferenceservice(namespace, svc.kserve_name)
        if not stable_kserve:
            raise ExternalServiceException("稳定版本 InferenceService 不存在")

        canary_storage_uri = f"s3://{settings.MINIO_BUCKET_PREFIX.rstrip('-')}-models/{canary_mv.storage_path}"
        resources = build_resource_spec(svc.cpu, svc.memory, svc.gpu_count)

        canary_body = build_canary_inferenceservice(
            stable_service=stable_kserve,
            canary_storage_uri=canary_storage_uri,
            resources=resources,
            replicas=svc.replicas,
            env_vars=svc.env_vars,
        )

        try:
            await create_inferenceservice(namespace, canary_body)
        except Exception as e:
            logger.error("Failed to create canary InferenceService for %s: %s", svc.kserve_name, e)
            raise ExternalServiceException(f"金丝雀 InferenceService 创建失败: {e}") from e

        canary_kserve_name = f"{svc.kserve_name}-canary"
        svc.canary_status = "deploying"
        svc.canary_model_version_id = request.canary_model_version_id
        svc.canary_traffic_percent = request.canary_traffic_percent
        svc.canary_kserve_name = canary_kserve_name

        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def update_canary_traffic(
        self,
        service_id: uuid.UUID,
        tenant_id: uuid.UUID,
        request: CanaryTrafficUpdateRequest,
    ) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)
        if svc.canary_status != "running":
            raise ConflictException("金丝雀必须处于运行状态才能调整流量")

        if request.canary_traffic_percent == 100:
            return await self._promote_canary(svc, tenant_id)
        if request.canary_traffic_percent == 0:
            return await self._rollback_canary(svc, tenant_id)

        svc.canary_traffic_percent = request.canary_traffic_percent
        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def promote_canary(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)
        if svc.canary_status != "running":
            raise ConflictException("金丝雀必须处于运行状态才能提升")
        return await self._promote_canary(svc, tenant_id)

    async def rollback_canary(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)
        if svc.canary_status not in ("running", "failed"):
            raise ConflictException("金丝雀必须处于运行或失败状态才能回滚")
        return await self._rollback_canary(svc, tenant_id)

    async def _promote_canary(self, svc: InferenceService, tenant_id: uuid.UUID) -> InferenceService:
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        assert svc.canary_model_version_id is not None
        canary_mv = await self._get_model_version_or_fail(svc.canary_model_version_id)
        canary_storage_uri = f"s3://{settings.MINIO_BUCKET_PREFIX.rstrip('-')}-models/{canary_mv.storage_path}"

        assert svc.kserve_name is not None
        await patch_inferenceservice(
            namespace,
            svc.kserve_name,
            {
                "spec": {
                    "predictor": {
                        "model": {
                            "storageUri": canary_storage_uri,
                        }
                    }
                }
            },
        )

        if svc.canary_kserve_name:
            try:
                await delete_inferenceservice(namespace, svc.canary_kserve_name)
            except Exception as e:
                logger.warning("Failed to delete canary InferenceService %s: %s", svc.canary_kserve_name, e)

        if svc.scaling_mode == "auto" and svc.kserve_name:
            try:
                deploy_name = f"{svc.kserve_name}-predictor"
                scaled_obj = build_scaled_object(
                    name=f"{svc.kserve_name}{KEDA_SCALER_SUFFIX}",
                    namespace=namespace,
                    deploy_name=deploy_name,
                    min_replicas=svc.min_replicas,
                    max_replicas=svc.max_replicas,
                    metric_type=svc.target_metric_type,  # type: ignore[arg-type]
                    metric_value=svc.target_metric_value,  # type: ignore[arg-type]
                    cooldown_period=svc.cooldown_period,
                    polling_interval=svc.polling_interval,
                )
                await patch_scaled_object(
                    namespace,
                    f"{svc.kserve_name}{KEDA_SCALER_SUFFIX}",
                    {"spec": scaled_obj["spec"]},
                )
            except Exception as e:
                logger.warning("Failed to rebuild ScaledObject after promote: %s", e)

        assert svc.canary_model_version_id is not None
        svc.model_version_id = svc.canary_model_version_id
        self._clear_canary_fields(svc)
        svc.status = InferenceServiceStatus.DEPLOYING

        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def _rollback_canary(self, svc: InferenceService, tenant_id: uuid.UUID) -> InferenceService:
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if svc.canary_kserve_name:
            try:
                await delete_inferenceservice(namespace, svc.canary_kserve_name)
            except Exception as e:
                logger.warning("Failed to delete canary InferenceService %s: %s", svc.canary_kserve_name, e)

        if svc.scaling_mode == "auto" and svc.canary_kserve_name:
            try:
                await delete_scaled_object(namespace, f"{svc.canary_kserve_name}{KEDA_SCALER_SUFFIX}")
            except Exception as e:
                logger.debug("Cleanup: ScaledObject %s deletion skipped: %s", svc.canary_kserve_name, e)

        self._clear_canary_fields(svc)

        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    def _clear_canary_fields(self, svc: InferenceService) -> None:
        svc.canary_status = "none"
        svc.canary_model_version_id = None
        svc.canary_traffic_percent = None
        svc.canary_kserve_name = None

    async def _cleanup_canary_k8s_resources(self, svc: InferenceService, namespace: str) -> None:
        if not svc.canary_kserve_name:
            return
        try:
            await delete_inferenceservice(namespace, svc.canary_kserve_name)
        except Exception as e:
            logger.warning("Failed to delete canary InferenceService %s: %s", svc.canary_kserve_name, e)
        if svc.scaling_mode == "auto":
            try:
                await delete_scaled_object(namespace, f"{svc.canary_kserve_name}{KEDA_SCALER_SUFFIX}")
            except Exception as e:
                logger.debug("Cleanup: ScaledObject %s deletion skipped: %s", svc.canary_kserve_name, e)

    async def _sync_canary_scaling(
        self, svc: InferenceService, namespace: str, config: AutoScalingUpdateRequest
    ) -> None:
        if not svc.canary_kserve_name or svc.canary_status == "none":
            return

        if config.scaling_mode == "fixed":
            try:
                await patch_inferenceservice(
                    namespace,
                    svc.canary_kserve_name,
                    {
                        "spec": {
                            "predictor": {
                                "minReplicas": config.min_replicas,
                                "maxReplicas": config.max_replicas,
                            }
                        }
                    },
                )
            except Exception as e:
                logger.warning("Failed to sync canary fixed scaling for %s: %s", svc.canary_kserve_name, e)
        elif config.scaling_mode == "auto":
            try:
                deploy_name = f"{svc.canary_kserve_name}-predictor"
                scaled_obj = build_scaled_object(
                    name=f"{svc.canary_kserve_name}{KEDA_SCALER_SUFFIX}",
                    namespace=namespace,
                    deploy_name=deploy_name,
                    min_replicas=config.min_replicas,
                    max_replicas=config.max_replicas,
                    metric_type=config.target_metric_type,  # type: ignore[arg-type]
                    metric_value=config.target_metric_value,  # type: ignore[arg-type]
                    cooldown_period=config.cooldown_period,
                    polling_interval=config.polling_interval,
                )
                await create_scaled_object(namespace, scaled_obj)
                await patch_inferenceservice(
                    namespace,
                    svc.canary_kserve_name,
                    {
                        "spec": {
                            "predictor": {
                                "minReplicas": config.min_replicas,
                                "maxReplicas": config.max_replicas,
                            }
                        }
                    },
                )
            except Exception as e:
                logger.warning("Failed to sync canary auto scaling for %s: %s", svc.canary_kserve_name, e)

    async def get_canary_endpoint_url(self, svc: InferenceService, tenant_id: uuid.UUID) -> str | None:
        if not svc.canary_kserve_name or svc.canary_status != "running":
            return None
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        canary_obj = await get_inferenceservice(namespace, svc.canary_kserve_name)
        if not canary_obj:
            return None
        url: str | None = canary_obj.get("status", {}).get("url")
        return url

    async def list_inference_services(
        self,
        *,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        name: str | None = None,
    ) -> tuple[list[InferenceService], int]:
        query = select(InferenceService).where(InferenceService.tenant_id == tenant_id)

        if status:
            query = query.where(InferenceService.status == status)
        if name:
            query = query.where(InferenceService.name.ilike(f"%{name}%"))

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(InferenceService.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        services = list(result.scalars().all())

        non_terminal = [s for s in services if s.kserve_name and s.status not in TERMINAL_STATUSES]
        if non_terminal:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            for svc in non_terminal:
                try:
                    await self._sync_service_status(svc, namespace)
                except Exception as e:
                    logger.warning("Failed to sync status for %s: %s", svc.kserve_name, e)
            await self.db.commit()
            for svc in non_terminal:
                await self.db.refresh(svc)

        return services, total

    async def get_inference_service(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)
        if svc.kserve_name and svc.status not in TERMINAL_STATUSES:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            try:
                await self._sync_service_status(svc, namespace)
            except Exception as e:
                logger.warning("Failed to sync status for %s: %s", svc.kserve_name, e)
            await self.db.commit()
            await self.db.refresh(svc)
        return svc

    async def stop_inference_service(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.status not in (
            InferenceServiceStatus.RUNNING,
            InferenceServiceStatus.DEPLOYING,
            InferenceServiceStatus.PENDING,
        ):
            raise ConflictException(f"当前状态为 {svc.status}, 无法停止服务")

        if svc.kserve_name:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

            # Clean up canary if active
            if svc.canary_status != "none":
                await self._cleanup_canary_k8s_resources(svc, namespace)

            if svc.scaling_mode == "auto":
                try:
                    await delete_scaled_object(namespace, f"{svc.kserve_name}{KEDA_SCALER_SUFFIX}")
                except Exception as e:
                    logger.warning("Failed to delete ScaledObject for %s: %s", svc.kserve_name, e)

            try:
                await patch_inferenceservice(
                    namespace,
                    svc.kserve_name,
                    {"spec": {"predictor": {"minReplicas": 0}}},
                )
            except Exception as e:
                logger.warning("Failed to patch InferenceService %s: %s", svc.kserve_name, e)

        svc.status = InferenceServiceStatus.STOPPED
        svc.replicas = 0
        self._clear_canary_fields(svc)
        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def scale_inference_service(
        self, service_id: uuid.UUID, tenant_id: uuid.UUID, replicas: int
    ) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.status == InferenceServiceStatus.FAILED:
            raise ConflictException("服务处于异常状态, 请先修复后再进行扩缩容操作")

        if svc.scaling_mode == "auto":
            raise ConflictException("自动伸缩模式下不支持手动调整副本数, 请通过自动伸缩配置调整或先切换到手动模式")

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        # 扩容时检查 GPU 配额
        if replicas > svc.replicas and svc.gpu_count > 0:
            await self._check_gpu_quota(namespace, tenant.gpu_limit, svc.gpu_count * replicas)

        # K8s 更新
        if svc.kserve_name:
            await patch_inferenceservice(
                namespace,
                svc.kserve_name,
                {"spec": {"predictor": {"minReplicas": replicas, "maxReplicas": replicas}}},
            )

        # Sync canary replicas if active
        if svc.canary_kserve_name and svc.canary_status in ("running", "deploying"):
            try:
                await patch_inferenceservice(
                    namespace,
                    svc.canary_kserve_name,
                    {"spec": {"predictor": {"minReplicas": replicas, "maxReplicas": replicas}}},
                )
            except Exception as e:
                logger.warning("Failed to sync canary replicas for %s: %s", svc.canary_kserve_name, e)

        old_status = svc.status
        old_replicas = svc.replicas

        # DB 更新
        svc.replicas = replicas
        svc.min_replicas = replicas
        svc.max_replicas = replicas

        # 状态处理
        if old_status == InferenceServiceStatus.STOPPED and replicas > 0:
            svc.status = InferenceServiceStatus.DEPLOYING
        elif replicas == 0:
            svc.status = InferenceServiceStatus.STOPPED

        await self.db.commit()
        await self.db.refresh(svc)

        logger.info(
            "inference_service_scaled",
            extra={
                "service_id": str(svc.id),
                "tenant_id": str(tenant_id),
                "old_replicas": old_replicas,
                "new_replicas": replicas,
                "old_status": old_status,
                "new_status": svc.status,
            },
        )

        return svc

    async def delete_inference_service(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.kserve_name:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

            # Clean up canary if active
            if svc.canary_status != "none":
                await self._cleanup_canary_k8s_resources(svc, namespace)

            if svc.scaling_mode == "auto":
                try:
                    await delete_scaled_object(namespace, f"{svc.kserve_name}{KEDA_SCALER_SUFFIX}")
                except Exception as e:
                    logger.warning("Failed to delete ScaledObject for %s: %s", svc.kserve_name, e)

            try:
                await delete_inferenceservice(namespace, svc.kserve_name)
            except Exception as e:
                logger.warning("Failed to delete InferenceService %s: %s", svc.kserve_name, e)

        await self.db.delete(svc)
        await self.db.commit()
        return svc

    async def _sync_service_status(self, svc: InferenceService, namespace: str) -> None:
        if not svc.kserve_name:
            return
        kserve_obj = await get_inferenceservice(namespace, svc.kserve_name)
        if kserve_obj is None:
            return

        status_data: dict[str, Any] = kserve_obj.get("status", {})
        conditions: list[dict[str, str]] = status_data.get("conditions", [])

        if not conditions:
            return

        ready_condition = next(
            (c for c in conditions if c.get("type") == "Ready"),
            None,
        )

        if ready_condition is None:
            return

        if ready_condition.get("status") == "True":
            new_status = InferenceServiceStatus.RUNNING
            url = status_data.get("url")
            if url:
                svc.endpoint_url = url
            if not svc.proxy_endpoint:
                mv = await self.db.get(ModelVersion, svc.model_version_id)
                if mv:
                    rm = await self.db.get(RegisteredModel, mv.registered_model_id)
                    if rm:
                        svc.proxy_endpoint = (
                            f"{settings.API_BASE_URL}/api/inference-proxy/{svc.id}/v1/models/{rm.name}:predict"
                        )
        else:
            reason = ready_condition.get("reason", "")
            message = ready_condition.get("message", "")
            if "Progressing" in reason or "InProgress" in reason:
                new_status = InferenceServiceStatus.DEPLOYING
            else:
                new_status = InferenceServiceStatus.FAILED
                if message:
                    svc.error_message = message

        if new_status != svc.status:
            old_status = svc.status
            logger.info(
                "inference_service_status_changed",
                extra={
                    "service_id": str(svc.id),
                    "old_status": old_status,
                    "new_status": new_status,
                    "tenant_id": str(svc.tenant_id),
                    "reason": ready_condition.get("reason", ""),
                },
            )
            svc.status = new_status
            if new_status == InferenceServiceStatus.FAILED:
                try:
                    from sqlalchemy import true as sa_true

                    from app.models.enums import NotificationPriority, NotificationType, UserRole
                    from app.models.user import User as UserModel
                    from app.services.notification_service import NotificationService

                    notif_service = NotificationService(self.db)
                    result = await self.db.execute(
                        select(UserModel.id).where(
                            UserModel.tenant_id == svc.tenant_id,
                            UserModel.role.in_([UserRole.MLOPS, UserRole.ADMIN]),
                            UserModel.is_active == sa_true(),
                        )
                    )
                    user_ids = [row[0] for row in result.all()]
                    if svc.created_by not in user_ids:
                        user_ids.append(svc.created_by)
                    if user_ids:
                        await notif_service.create_notification_for_users(
                            user_ids=user_ids,
                            tenant_id=svc.tenant_id,
                            type=NotificationType.INFERENCE_SERVICE,
                            title="推理服务异常",
                            content=f"推理服务「{svc.name}」运行失败, 请及时处理.",
                            priority=NotificationPriority.HIGH,
                            resource_type="inference_service",
                            resource_id=str(svc.id),
                        )
                except Exception as e:
                    logger.warning("Failed to send inference failure notification for %s: %s", svc.id, e)

            # WebSocket push
            self._publish_status_change(svc.tenant_id, svc.id, old_status, new_status.value)
        if svc.canary_kserve_name:
            canary_obj = await get_inferenceservice(namespace, svc.canary_kserve_name)
            if canary_obj is None:
                svc.canary_status = "failed"
            else:
                canary_conditions = canary_obj.get("status", {}).get("conditions", [])
                canary_ready = next(
                    (c for c in canary_conditions if c.get("type") == "Ready"),
                    None,
                )
                if canary_ready and canary_ready.get("status") == "True":
                    svc.canary_status = "running"
                else:
                    svc.canary_status = "deploying"

    async def _check_gpu_quota(self, namespace: str, gpu_limit: int, requested: int) -> None:
        if requested == 0:
            return

        if gpu_limit <= 0:
            raise QuotaExceededException("租户 GPU 配额为 0, 无法创建需要 GPU 的推理服务")

        try:
            used = await get_quota_used(namespace)
            gpu_used = int(used.get("requests.nvidia.com/gpu", "0"))
        except Exception:
            gpu_used = 0

        if gpu_used + requested > gpu_limit:
            raise QuotaExceededException(
                f"GPU 配额不足: 已使用 {gpu_used} 张, 配额 {gpu_limit} 张, 请求 {requested} 张"
            )

    @staticmethod
    async def get_service_by_token(db: AsyncSession, token: str) -> InferenceService | None:
        token_hash = hash_api_token(token)
        result = await db.execute(select(InferenceService).where(InferenceService.auth_token_hash == token_hash))
        return result.scalar_one_or_none()

    async def _get_service_or_fail(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        result = await self.db.execute(
            select(InferenceService).where(InferenceService.id == service_id, InferenceService.tenant_id == tenant_id)
        )
        svc = result.scalar_one_or_none()
        if not svc:
            raise NotFoundException("推理服务不存在")
        return svc

    async def _get_tenant_or_fail(self, tenant_id: uuid.UUID) -> Tenant:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在")
        return tenant

    async def _get_model_version_or_fail(self, model_version_id: uuid.UUID) -> ModelVersion:
        result = await self.db.execute(select(ModelVersion).where(ModelVersion.id == model_version_id))
        version = result.scalar_one_or_none()
        if not version:
            raise NotFoundException("模型版本不存在")
        return version

    @staticmethod
    def _publish_status_change(
        tenant_id: uuid.UUID,
        service_id: uuid.UUID,
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
                event="inference.status_changed",
                payload={"id": str(service_id), "old_status": old_status, "new_status": new_status},
            )
        )
