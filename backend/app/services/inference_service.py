from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.core.exceptions import (
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.core.security import generate_api_token, hash_api_token
from app.core.ws_pubsub import publish_ws_event
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.deployment import (
    build_deployment,
    build_resource_spec,
    build_service,
    create_deployment,
    create_k8s_service,
    delete_deployment,
    delete_k8s_service,
    get_deployment,
    patch_deployment,
)
from app.integrations.k8s.inference_route import inference_access_url, inference_path, put_inference_route
from app.integrations.k8s.kubeai_volumes import (
    build_chown_init_container,
    build_kubeai_env_vars,
    build_kubeai_volumes,
    build_models_volume,
)
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.resource_quota import get_quota_used
from app.integrations.k8s.secret import ensure_registry_pull_secret
from app.integrations.keda.builder import build_scaled_object
from app.integrations.keda.client import (
    create_scaled_object,
    delete_scaled_object,
    patch_scaled_object,
)
from app.models.enums import ImageCategory, InferenceServiceStatus
from app.models.image import Image
from app.models.inference_service import InferenceService
from app.models.registered_model import ModelVersion
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.inference_service import AutoScalingConfig

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.integrations.prometheus.client import PrometheusClient
    from app.schemas.inference_service import AutoScalingUpdateRequest

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
        gpu_count: int = 0,
        cpu: str = "2",
        memory: str = "4Gi",
        replicas: int = 1,
        image: str | None = None,
        image_id: uuid.UUID | None = None,
        container_port: int | None = None,
        command: list[str] | None = None,
        args: list[str] | None = None,
        env_vars: dict[str, str] | None = None,
        description: str | None = None,
        auto_scaling: AutoScalingConfig | None = None,
        model_version_id: uuid.UUID | None = None,
        subpath_mode: str = "rewrite",
    ) -> tuple[InferenceService, str]:
        svc, tenant, api_token = await self._create_inference_service_record(
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            replicas=replicas,
            image=image,
            image_id=image_id,
            container_port=container_port,
            command=command,
            args=args,
            env_vars=env_vars,
            description=description,
            auto_scaling=auto_scaling,
            model_version_id=model_version_id,
            subpath_mode=subpath_mode,
        )
        await self._deploy_inference_service_resources(svc=svc, tenant=tenant)
        await self.db.refresh(svc)
        return svc, api_token

    async def create_inference_service_record(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        gpu_count: int = 0,
        cpu: str = "2",
        memory: str = "4Gi",
        replicas: int = 1,
        image: str | None = None,
        image_id: uuid.UUID | None = None,
        container_port: int | None = None,
        command: list[str] | None = None,
        args: list[str] | None = None,
        env_vars: dict[str, str] | None = None,
        description: str | None = None,
        auto_scaling: AutoScalingConfig | None = None,
        model_version_id: uuid.UUID | None = None,
        subpath_mode: str = "rewrite",
    ) -> tuple[InferenceService, str]:
        svc, _, api_token = await self._create_inference_service_record(
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            replicas=replicas,
            image=image,
            image_id=image_id,
            container_port=container_port,
            command=command,
            args=args,
            env_vars=env_vars,
            description=description,
            auto_scaling=auto_scaling,
            model_version_id=model_version_id,
            subpath_mode=subpath_mode,
        )
        return svc, api_token

    async def _create_inference_service_record(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        gpu_count: int = 0,
        cpu: str = "2",
        memory: str = "4Gi",
        replicas: int = 1,
        image: str | None = None,
        image_id: uuid.UUID | None = None,
        container_port: int | None = None,
        command: list[str] | None = None,
        args: list[str] | None = None,
        env_vars: dict[str, str] | None = None,
        description: str | None = None,
        auto_scaling: AutoScalingConfig | None = None,
        model_version_id: uuid.UUID | None = None,
        subpath_mode: str = "rewrite",
    ) -> tuple[InferenceService, Tenant, str]:
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
            image=image,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            replicas=replicas,
            min_replicas=min_rep,
            max_replicas=max_rep,
            scaling_mode="auto" if is_auto else "fixed",
            subpath_mode=subpath_mode,
            status=InferenceServiceStatus.PENDING,
            description=description,
            env_vars=env_vars,
            auth_token_hash=hash_api_token(api_token),
        )
        if model_version_id is not None:
            await self._get_model_version_or_fail(model_version_id)
            svc_kwargs["model_version_id"] = model_version_id
        # 运行时镜像 (从 inference 类镜像解析) / 端口 / 命令. 模型/代码可打进镜像或放挂载卷.
        if image_id is not None:
            svc_kwargs["image"] = await self._resolve_image_ref(image_id, tenant_id)
        svc_kwargs["container_port"] = container_port
        svc_kwargs["command"] = json.dumps(command) if command else None
        svc_kwargs["args"] = json.dumps(args) if args else None
        if is_auto and auto_scaling is not None:
            svc_kwargs["target_metric_type"] = auto_scaling.target_metric_type
            svc_kwargs["target_metric_value"] = auto_scaling.target_metric_value
            svc_kwargs["cooldown_period"] = auto_scaling.cooldown_period
            svc_kwargs["polling_interval"] = auto_scaling.polling_interval

        svc = InferenceService(**svc_kwargs)
        self.db.add(svc)
        await self.db.flush()
        svc.proxy_endpoint = inference_access_url(svc.id)
        await self.db.commit()
        await self.db.refresh(svc)
        return svc, tenant, api_token

    async def deploy_inference_service(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        return await self._deploy_inference_service_resources(svc=svc, tenant=tenant)

    async def _deploy_inference_service_resources(self, *, svc: InferenceService, tenant: Tenant) -> InferenceService:
        if svc.status not in (InferenceServiceStatus.PENDING, InferenceServiceStatus.DEPLOYING):
            logger.info("skip_inference_service_deploy", extra={"service_id": str(svc.id), "status": svc.status})
            return svc

        old_status = svc.status
        svc.status = InferenceServiceStatus.DEPLOYING
        svc.error_message = None
        await self.db.commit()
        if old_status != svc.status:
            await self._publish_status_change(svc.tenant_id, svc.id, old_status, svc.status)

        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
        is_auto = svc.scaling_mode == "auto"
        auto_scaling = (
            AutoScalingConfig(
                scaling_mode="auto",
                min_replicas=svc.min_replicas,
                max_replicas=svc.max_replicas,
                target_metric_type=svc.target_metric_type,  # type: ignore[arg-type]
                target_metric_value=svc.target_metric_value,
                cooldown_period=svc.cooldown_period,
                polling_interval=svc.polling_interval,
            )
            if is_auto
            else None
        )
        k8s_name = svc.k8s_deployment_name or f"inference-{sanitize_k8s_name(svc.name)}"
        resources = build_resource_spec(svc.cpu, svc.memory, svc.gpu_count)
        command = json.loads(svc.command) if svc.command else None
        args = json.loads(svc.args) if svc.args else None
        # 推理 Pod 对齐开发环境: 挂 per-user home + 租户 workspace (hostPath), 需创建者 username.
        user = await self._get_user_or_fail(svc.created_by)

        await self._create_k8s_resources(
            svc=svc,
            namespace=namespace,
            k8s_name=k8s_name,
            tenant_name=tenant.name,
            username=user.username,
            image=svc.image,  # type: ignore[arg-type]
            container_port=svc.container_port,  # type: ignore[arg-type]
            command=command,
            args=args,
            resources=resources,
            replicas=svc.replicas,
            min_rep=svc.min_replicas,
            max_rep=svc.max_replicas,
            env_vars=svc.env_vars,
            is_auto=is_auto,
            auto_scaling=auto_scaling,
            model_version_id=svc.model_version_id,
        )

        svc.status = InferenceServiceStatus.DEPLOYING
        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def _create_k8s_resources(
        self,
        *,
        svc: InferenceService,
        namespace: str,
        k8s_name: str,
        tenant_name: str,
        username: str,
        image: str,
        container_port: int,
        command: list[str] | None,
        args: list[str] | None,
        resources: dict[str, Any],
        replicas: int,
        min_rep: int,
        max_rep: int,
        env_vars: dict[str, str] | None,
        is_auto: bool,
        auto_scaling: AutoScalingConfig | None,
        model_version_id: uuid.UUID | None = None,
        subpath_mode: str = "rewrite",
    ) -> None:
        # 可选镜像拉取 secret (Harbor). 未配置 Harbor 时回退到无 pull secret (不阻塞).
        image_pull_secrets: list[str] | None = None
        try:
            image_pull_secrets = [await ensure_registry_pull_secret(namespace)]
        except Exception as e:
            logger.debug("registry pull secret not ensured for %s: %s", namespace, e)

        # 挂 per-user home + 租户 workspace (对齐开发环境); chown initContainer 修归属供非根主容器写.
        volumes, volume_mounts = build_kubeai_volumes(username=username, tenant_name=tenant_name)
        init_containers: list[dict[str, Any]] = []

        # 可选模型版本: 挂载本地模型版本目录到 /kubeai/models (文件已由 backend 写入 hostPath,
        # 推理 Pod 直接读, 无需 model-pull initContainer).
        if model_version_id is not None:
            model_version = await self._get_model_version_db(model_version_id)
            model_vol, model_mnt = build_models_volume(tenant_name, model_version.storage_path)
            volumes.append(model_vol)
            volume_mounts.append(model_mnt)

        init_containers.append(build_chown_init_container(name="inference-init", volume_mounts=volume_mounts))
        final_env_vars = build_kubeai_env_vars(extra=env_vars)
        # 注入 BASE_URL_PREFIX (= /inference/<hex>) —— 告知应用平台对外访问前缀.
        # 两种子路径模式都注入: rewrite 模式下应用仅用于拼外部 URL(OpenAPI docs / 跳转 /
        # 前端 fetch), native 模式下应用还据此做路由(自行 StripPrefix). 见 inference_route.
        final_env_vars["BASE_URL_PREFIX"] = inference_path(svc.id)

        dep_body = build_deployment(
            name=k8s_name,
            namespace=namespace,
            image=image,
            container_port=container_port,
            command=command,
            args=args,
            replicas=replicas,
            resources=resources,
            env_vars=final_env_vars,
            security_context={"runAsUser": 1000, "runAsGroup": 100, "runAsNonRoot": True},
            init_containers=init_containers,
            volumes=volumes,
            volume_mounts=volume_mounts,
            image_pull_secrets=image_pull_secrets,
            node_selector={"kubeai": "true"},
        )

        try:
            await create_deployment(namespace, dep_body)
        except Exception as e:
            logger.error("Failed to create Deployment %s: %s", k8s_name, e)
            svc.status = InferenceServiceStatus.FAILED
            await self.db.commit()
            raise

        svc_body = build_service(
            name=k8s_name,
            namespace=namespace,
            target_port=container_port,
            deployment_name=k8s_name,
        )
        try:
            await create_k8s_service(namespace, svc_body)
        except Exception as e:
            logger.error("Failed to create Service %s: %s", k8s_name, e)
            with contextlib.suppress(Exception):
                await delete_deployment(namespace, k8s_name)
            svc.status = InferenceServiceStatus.FAILED
            await self.db.commit()
            raise

        if is_auto and auto_scaling is not None:
            try:
                scaled_obj = build_scaled_object(
                    name=f"{k8s_name}{KEDA_SCALER_SUFFIX}",
                    namespace=namespace,
                    deploy_name=k8s_name,
                    min_replicas=min_rep,
                    max_replicas=max_rep,
                    metric_type=auto_scaling.target_metric_type,  # type: ignore[arg-type]
                    metric_value=auto_scaling.target_metric_value,  # type: ignore[arg-type]
                    cooldown_period=auto_scaling.cooldown_period,
                    polling_interval=auto_scaling.polling_interval,
                )
                await create_scaled_object(namespace, scaled_obj)
            except Exception as e:
                logger.error("Failed to create ScaledObject for %s: %s", k8s_name, e)
                with contextlib.suppress(Exception):
                    await delete_deployment(namespace, k8s_name)
                    await delete_k8s_service(namespace, k8s_name)
                svc.status = InferenceServiceStatus.FAILED
                svc.error_message = f"自动伸缩配置失败: {e}"
                await self.db.commit()
                raise ExternalServiceException(f"KEDA 自动伸缩配置失败, 请确认集群已安装 KEDA: {e}") from e

        svc.k8s_deployment_name = k8s_name
        svc.k8s_service_name = k8s_name

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
            keda_name = self._get_keda_name(svc)
            try:
                await delete_scaled_object(namespace, keda_name)
            except Exception as e:
                logger.warning("Failed to delete ScaledObject for %s: %s", keda_name, e)

            target_rep = svc.replicas if svc.replicas > 0 else 1
            if svc.k8s_deployment_name:
                await patch_deployment(namespace, svc.k8s_deployment_name, {"spec": {"replicas": target_rep}})
            svc.min_replicas = target_rep
            svc.max_replicas = target_rep
            svc.scaling_mode = "fixed"
            svc.target_metric_type = None
            svc.target_metric_value = None

        elif new_mode == "auto" and old_mode == "fixed":
            deploy_name = self._get_deploy_name(svc)
            keda_name = self._get_keda_name(svc)
            scaled_obj = build_scaled_object(
                name=keda_name,
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

            if svc.k8s_deployment_name:
                await patch_deployment(namespace, svc.k8s_deployment_name, {"spec": {"replicas": config.min_replicas}})
            svc.scaling_mode = "auto"
            svc.min_replicas = config.min_replicas
            svc.max_replicas = config.max_replicas
            svc.target_metric_type = config.target_metric_type
            svc.target_metric_value = config.target_metric_value
            svc.cooldown_period = config.cooldown_period
            svc.polling_interval = config.polling_interval

        elif new_mode == "auto" and old_mode == "auto":
            keda_name = self._get_keda_name(svc)
            scaled_obj_body = {
                "spec": {
                    "minReplicaCount": config.min_replicas,
                    "maxReplicaCount": config.max_replicas,
                    "cooldownPeriod": config.cooldown_period,
                    "pollingInterval": config.polling_interval,
                    "triggers": build_scaled_object(
                        name=keda_name,
                        namespace=namespace,
                        deploy_name=self._get_deploy_name(svc),
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
                await patch_scaled_object(namespace, keda_name, scaled_obj_body)
            except Exception as e:
                raise ExternalServiceException(f"KEDA 伸缩配置更新失败: {e}") from e

            if svc.k8s_deployment_name:
                await patch_deployment(namespace, svc.k8s_deployment_name, {"spec": {"replicas": config.min_replicas}})
            svc.min_replicas = config.min_replicas
            svc.max_replicas = config.max_replicas
            svc.target_metric_type = config.target_metric_type
            svc.target_metric_value = config.target_metric_value
            svc.cooldown_period = config.cooldown_period
            svc.polling_interval = config.polling_interval

        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def regenerate_token(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
        svc = await self._get_service_or_fail(service_id, tenant_id)
        new_token = generate_api_token()
        svc.auth_token_hash = hash_api_token(new_token)
        await self.db.commit()
        return new_token

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

        non_terminal = [s for s in services if s.k8s_deployment_name and s.status not in TERMINAL_STATUSES]
        if non_terminal:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            for svc in non_terminal:
                try:
                    await self._sync_service_status(svc, namespace)
                except Exception as e:
                    logger.warning("Failed to sync status for %s: %s", svc.k8s_deployment_name, e)
            await self.db.commit()
            for svc in non_terminal:
                await self.db.refresh(svc)

        return services, total

    async def get_inference_service(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)
        if svc.k8s_deployment_name and svc.status not in TERMINAL_STATUSES:
            tenant = await self._get_tenant_or_fail(tenant_id)
            namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
            try:
                await self._sync_service_status(svc, namespace)
            except Exception as e:
                logger.warning("Failed to sync status for %s: %s", svc.k8s_deployment_name, e)
            await self.db.commit()
            await self.db.refresh(svc)
        return svc

    async def sync_non_terminal_inference_services(self, *, limit: int = 200) -> int:
        result = await self.db.execute(
            select(InferenceService)
            .where(
                InferenceService.status.in_([status.value for status in NON_TERMINAL_STATUSES]),
                InferenceService.k8s_deployment_name.is_not(None),
            )
            .order_by(InferenceService.updated_at.asc())
            .limit(limit)
        )
        services = list(result.scalars().all())
        if not services:
            return 0

        synced_count = 0
        for svc in services:
            try:
                tenant = await self._get_tenant_or_fail(svc.tenant_id)
                namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
                await self._sync_service_status(svc, namespace)
                synced_count += 1
            except Exception as e:
                logger.warning("Failed to sync status for inference service %s: %s", svc.k8s_deployment_name, e)

        await self.db.commit()
        return synced_count

    async def start_inference_service(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        """标记推理服务为启动中 (仅 DB 操作, K8s 由 Taskiq worker 异步执行)."""
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.status != InferenceServiceStatus.STOPPED:
            raise ConflictException(f"当前状态为 {svc.status}, 无法启动服务")

        target_replicas = svc.min_replicas if svc.min_replicas > 0 else 1

        svc.status = InferenceServiceStatus.DEPLOYING
        svc.replicas = target_replicas
        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def execute_inference_service_start(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """由 Taskiq worker 调用: 执行 K8s 启动操作 (patch + KEDA)."""
        svc = await self._get_service_or_fail(service_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        is_auto = svc.scaling_mode == "auto"
        target_replicas = svc.replicas
        max_rep = svc.max_replicas if is_auto else target_replicas

        if svc.gpu_count > 0:
            gpu_needed = svc.gpu_count * max_rep if is_auto else svc.gpu_count * target_replicas
            await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_needed)

        if svc.k8s_deployment_name:
            await patch_deployment(namespace, svc.k8s_deployment_name, {"spec": {"replicas": target_replicas}})

        if is_auto and svc.k8s_deployment_name:
            scaled_obj = build_scaled_object(
                name=self._get_keda_name(svc),
                namespace=namespace,
                deploy_name=svc.k8s_deployment_name,
                min_replicas=target_replicas,
                max_replicas=max_rep,
                metric_type=svc.target_metric_type,  # type: ignore[arg-type]
                metric_value=svc.target_metric_value,  # type: ignore[arg-type]
                cooldown_period=svc.cooldown_period,
                polling_interval=svc.polling_interval,
            )
            try:
                await create_scaled_object(namespace, scaled_obj)
            except Exception as e:
                logger.error("Failed to create ScaledObject on start for %s: %s", svc.id, e)

    async def stop_inference_service(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        """标记推理服务为已停止 (仅 DB 操作, K8s 清理由 Taskiq worker 异步执行)."""
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.status not in (
            InferenceServiceStatus.RUNNING,
            InferenceServiceStatus.DEPLOYING,
            InferenceServiceStatus.PENDING,
        ):
            raise ConflictException(f"当前状态为 {svc.status}, 无法停止服务")

        svc.status = InferenceServiceStatus.STOPPED
        svc.replicas = 0
        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def execute_inference_service_stop(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """由 Taskiq worker 调用: 执行 K8s 停止清理 (KEDA + scale-to-zero)."""
        svc = await self._get_service_or_fail(service_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if svc.scaling_mode == "auto":
            keda_name = self._get_keda_name(svc)
            try:
                await delete_scaled_object(namespace, keda_name)
            except Exception as e:
                logger.warning("Failed to delete ScaledObject: %s", e)

        if svc.k8s_deployment_name:
            try:
                await patch_deployment(namespace, svc.k8s_deployment_name, {"spec": {"replicas": 0}})
            except Exception as e:
                logger.warning("Failed to patch Deployment %s: %s", svc.k8s_deployment_name, e)

    async def scale_inference_service(
        self, service_id: uuid.UUID, tenant_id: uuid.UUID, replicas: int
    ) -> InferenceService:
        """更新推理服务副本数 (仅 DB 操作, K8s patch 由 Taskiq worker 异步执行)."""
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.status == InferenceServiceStatus.FAILED:
            raise ConflictException("服务处于异常状态, 请先修复后再进行扩缩容操作")

        if svc.scaling_mode == "auto":
            raise ConflictException("自动伸缩模式下不支持手动调整副本数, 请通过自动伸缩配置调整或先切换到手动模式")

        old_status = svc.status
        old_replicas = svc.replicas

        svc.replicas = replicas
        svc.min_replicas = replicas
        svc.max_replicas = replicas

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

    async def execute_inference_service_scale(self, service_id: uuid.UUID, tenant_id: uuid.UUID, replicas: int) -> None:
        """由 Taskiq worker 调用: 执行 K8s 扩缩容 patch."""
        svc = await self._get_service_or_fail(service_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        if svc.k8s_deployment_name:
            await patch_deployment(namespace, svc.k8s_deployment_name, {"spec": {"replicas": replicas}})

    async def delete_inference_service(self, service_id: uuid.UUID, tenant_id: uuid.UUID) -> InferenceService:
        """删除推理服务 DB 记录 (K8s 清理由 Taskiq worker 异步执行)."""
        svc = await self._get_service_or_fail(service_id, tenant_id)
        await self.db.delete(svc)
        await self.db.commit()
        return svc

    @staticmethod
    async def cleanup_k8s_resources(
        *,
        namespace: str,
        scaling_mode: str,
        k8s_deployment_name: str | None = None,
        k8s_service_name: str | None = None,
    ) -> None:
        """清理 K8s 资源 (无 DB 依赖, 用于 Taskiq delete 任务)."""
        if scaling_mode == "auto" and k8s_deployment_name:
            try:
                await delete_scaled_object(namespace, f"{k8s_deployment_name}{KEDA_SCALER_SUFFIX}")
            except Exception as e:
                logger.warning("Failed to delete ScaledObject: %s", e)

        if k8s_deployment_name:
            try:
                await delete_deployment(namespace, k8s_deployment_name)
            except Exception as e:
                logger.warning("Failed to delete Deployment %s: %s", k8s_deployment_name, e)
        if k8s_service_name:
            try:
                await delete_k8s_service(namespace, k8s_service_name)
            except Exception as e:
                logger.warning("Failed to delete Service %s: %s", k8s_service_name, e)

    async def _sync_service_status(self, svc: InferenceService, namespace: str) -> None:
        if not svc.k8s_deployment_name:
            return
        dep = await get_deployment(namespace, svc.k8s_deployment_name)
        if dep is None:
            return

        status_data: dict[str, Any] = dep.get("status", {})
        replicas = status_data.get("replicas", 0) or 0
        ready_replicas = status_data.get("ready_replicas", 0) or 0
        unavailable = status_data.get("unavailable_replicas", 0) or 0
        conditions: list[dict[str, str]] = status_data.get("conditions", [])

        if replicas > 0 and ready_replicas >= replicas:
            new_status = InferenceServiceStatus.RUNNING
            if svc.k8s_service_name and svc.container_port:
                svc.endpoint_url = f"http://{svc.k8s_service_name}.{namespace}.svc.cluster.local:{svc.container_port}"
                svc.proxy_endpoint = inference_access_url(svc.id)
        elif replicas > 0 and (unavailable > 0 or ready_replicas < replicas):
            progressing = next(
                (c for c in conditions if c.get("type") == "Progressing" and c.get("status") == "False"),
                None,
            )
            if progressing:
                new_status = InferenceServiceStatus.FAILED
                svc.error_message = progressing.get("message", "")
            else:
                new_status = InferenceServiceStatus.DEPLOYING
        elif replicas == 0:
            new_status = InferenceServiceStatus.STOPPED
        else:
            return

        if new_status != svc.status:
            old_status = svc.status
            logger.info(
                "inference_service_status_changed",
                extra={
                    "service_id": str(svc.id),
                    "old_status": old_status,
                    "new_status": new_status,
                    "tenant_id": str(svc.tenant_id),
                },
            )
            svc.status = new_status
            if new_status == InferenceServiceStatus.FAILED:
                await self._send_failure_notification(svc)
            await self._publish_status_change(svc.tenant_id, svc.id, old_status, new_status.value)

        if new_status == InferenceServiceStatus.RUNNING:
            await put_inference_route(svc, namespace)

    def _get_deploy_name(self, svc: InferenceService) -> str:
        return svc.k8s_deployment_name or ""

    def _get_keda_name(self, svc: InferenceService) -> str:
        return f"{svc.k8s_deployment_name}{KEDA_SCALER_SUFFIX}" if svc.k8s_deployment_name else ""

    async def _send_failure_notification(self, svc: InferenceService) -> None:
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

    async def _get_user_or_fail(self, user_id: uuid.UUID) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")
        return user

    async def _get_model_version_or_fail(self, model_version_id: uuid.UUID) -> ModelVersion:
        result = await self.db.execute(select(ModelVersion).where(ModelVersion.id == model_version_id))
        version = result.scalar_one_or_none()
        if not version:
            raise NotFoundException("模型版本不存在")
        return version

    async def _get_model_version_db(self, model_version_id: uuid.UUID) -> ModelVersion:
        """Return ModelVersion or raise NotFoundException (same as _get_model_version_or_fail)."""
        return await self._get_model_version_or_fail(model_version_id)

    async def _resolve_image_ref(self, image_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
        result = await self.db.execute(
            select(Image).where(
                Image.id == image_id,
                Image.is_enabled == True,  # noqa: E712
                Image.deleted_at.is_(None),
            )
        )
        img = result.scalar_one_or_none()
        if not img:
            raise NotFoundException("镜像不存在或不可用")
        if img.tenant_id is not None and img.tenant_id != tenant_id:
            raise NotFoundException("镜像不存在或不可用")
        if img.category != ImageCategory.INFERENCE.value:
            raise NotFoundException("该镜像非推理类镜像, 不可用于推理服务")
        return img.image_ref

    async def get_metrics(
        self,
        *,
        service_id: uuid.UUID,
        tenant_id: uuid.UUID,
        prom_client: PrometheusClient | None,
        duration: str = "20m",
        step: str = "15s",
    ) -> dict[str, Any]:
        """Query Prometheus for GPU metrics of inference service pods."""
        svc = await self.get_inference_service(service_id, tenant_id)
        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        # Build metrics_url from running pods
        metrics_url: str | None = None
        try:
            pod_name = await self._get_running_pod_name(svc, namespace)
            if pod_name and svc.container_port:
                from kubernetes_asyncio import client as k8s_client

                from app.integrations.k8s.client import get_k8s_clients

                clients = await get_k8s_clients()
                core_v1 = k8s_client.CoreV1Api(clients["api_client"])
                pod_obj = await core_v1.read_namespaced_pod(pod_name, namespace)
                if pod_obj.status and pod_obj.status.pod_ip:
                    metrics_url = f"http://{pod_obj.status.pod_ip}:{svc.container_port}"
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
            pod_name = await self._get_running_pod_name(svc, namespace)

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
    async def _get_running_pod_name(svc: InferenceService, namespace: str) -> str | None:
        """Find the first running pod name for the inference service."""
        from kubernetes_asyncio import client as k8s_client

        from app.integrations.k8s.client import get_k8s_clients

        try:
            clients = await get_k8s_clients()
            core_v1 = k8s_client.CoreV1Api(clients["api_client"])

            label_selector = f"app.kubernetes.io/name={svc.k8s_deployment_name}" if svc.k8s_deployment_name else ""
            pods_resp = await core_v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)

            running_pods = [p.metadata.name for p in pods_resp.items if p.status and p.status.phase == "Running"]
            return running_pods[0] if running_pods else None
        except Exception as e:
            logger.warning("Failed to list pods for inference service metrics: %s", e)
            return None

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

    @staticmethod
    async def _publish_status_change(
        tenant_id: uuid.UUID,
        service_id: uuid.UUID,
        old_status: str,
        new_status: str,
    ) -> None:
        await publish_ws_event(
            tenant_id=tenant_id,
            event="inference.status_changed",
            payload={"id": str(service_id), "old_status": old_status, "new_status": new_status},
        )
