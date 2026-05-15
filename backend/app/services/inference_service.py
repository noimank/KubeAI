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
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.resource_quota import get_quota_used
from app.integrations.kserve.builder import build_inferenceservice, build_resource_spec
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

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {InferenceServiceStatus.FAILED, InferenceServiceStatus.STOPPED}
NON_TERMINAL_STATUSES = {
    InferenceServiceStatus.PENDING,
    InferenceServiceStatus.DEPLOYING,
    InferenceServiceStatus.RUNNING,
}


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
    ) -> tuple[InferenceService, str]:
        model_version = await self._get_model_version_or_fail(model_version_id)

        tenant = await self._get_tenant_or_fail(tenant_id)
        namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

        await self._check_gpu_quota(namespace, tenant.gpu_limit, gpu_count * replicas)

        api_token = generate_api_token()

        svc = InferenceService(
            tenant_id=tenant_id,
            created_by=user_id,
            name=name,
            model_version_id=model_version_id,
            image=image,
            gpu_count=gpu_count,
            cpu=cpu,
            memory=memory,
            replicas=replicas,
            min_replicas=replicas,
            max_replicas=replicas,
            status=InferenceServiceStatus.PENDING,
            description=description,
            env_vars=env_vars,
            auth_token_hash=hash_api_token(api_token),
        )
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

        svc.kserve_name = kserve_name
        svc.status = InferenceServiceStatus.DEPLOYING
        await self.db.commit()
        await self.db.refresh(svc)
        return svc, api_token

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
        await self.db.commit()
        await self.db.refresh(svc)
        return svc

    async def scale_inference_service(
        self, service_id: uuid.UUID, tenant_id: uuid.UUID, replicas: int
    ) -> InferenceService:
        svc = await self._get_service_or_fail(service_id, tenant_id)

        if svc.status == InferenceServiceStatus.FAILED:
            raise ConflictException("服务处于异常状态, 请先修复后再进行扩缩容操作")

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
            logger.info(
                "inference_service_status_changed",
                extra={
                    "service_id": str(svc.id),
                    "old_status": svc.status,
                    "new_status": new_status,
                    "tenant_id": str(svc.tenant_id),
                    "reason": ready_condition.get("reason", ""),
                },
            )
            svc.status = new_status

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
