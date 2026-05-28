import logging
import random
import uuid

import httpx
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import UnauthorizedException
from app.integrations.kserve.client import get_inferenceservice
from app.models.enums import InferenceServiceStatus
from app.services.audit_service import AuditService
from app.services.inference_service import InferenceServiceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inference-proxy", tags=["inference-proxy"])


def _extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/{service_id}/{path:path}")
async def proxy_inference_request(
    service_id: uuid.UUID,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Response:
    token = _extract_bearer_token(request)
    if not token:
        raise UnauthorizedException("未提供认证 Token")

    svc = await InferenceServiceService.get_service_by_token(db, token)
    if not svc or svc.id != service_id:
        raise UnauthorizedException("无效的 API Token")

    if svc.status != InferenceServiceStatus.RUNNING:
        return Response(
            content='{"error": "推理服务未就绪"}',
            status_code=503,
            media_type="application/json",
        )

    if not svc.endpoint_url:
        return Response(
            content='{"error": "推理端点不可用"}',
            status_code=503,
            media_type="application/json",
        )

    # Canary traffic routing (only for model services)
    is_canary = False
    target_base_url = svc.endpoint_url

    if svc.service_type != "custom" and svc.canary_status == "running" and svc.canary_kserve_name:
        canary_url = await _get_canary_endpoint_url(svc, db)
        if canary_url:
            rand = random.randint(0, 99)
            if rand < (svc.canary_traffic_percent or 0):
                target_base_url = canary_url
                is_canary = True

    target_url = f"{target_base_url}/{path}"

    body = await request.body()
    headers = {}
    if request.headers.get("Content-Type"):
        headers["Content-Type"] = request.headers["Content-Type"]
    if request.headers.get("Accept"):
        headers["Accept"] = request.headers["Accept"]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=headers,
            )
    except httpx.RequestError as e:
        logger.error("Proxy request to %s failed: %s", target_url, e)
        return Response(
            content='{"error": "推理服务不可达"}',
            status_code=502,
            media_type="application/json",
        )

    try:
        audit_svc = AuditService(db)
        await audit_svc.log_action(
            action="proxy_request",
            resource_type="inference_services",
            resource_id=str(service_id),
            ip_address=_get_client_ip(request),
            tenant_id=svc.tenant_id,
            detail={"canary": is_canary},
        )
        await db.commit()
    except Exception:
        logger.warning("Failed to write audit log for proxy request", exc_info=True)

    excluded_headers = {"transfer-encoding", "content-encoding", "content-length"}
    response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}
    response_headers["X-KubeAI-Canary"] = "true" if is_canary else "false"

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers,
        media_type=resp.headers.get("Content-Type"),
    )


async def _get_canary_endpoint_url(svc: object, db: AsyncSession) -> str | None:
    from app.integrations.k8s.namespace import make_namespace_name
    from app.models.tenant import Tenant

    tenant_id = getattr(svc, "tenant_id", None)
    canary_kserve_name = getattr(svc, "canary_kserve_name", None)
    if not tenant_id or not canary_kserve_name:
        return None

    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        return None

    namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)
    canary_obj = await get_inferenceservice(namespace, canary_kserve_name)
    if not canary_obj:
        return None
    url: str | None = canary_obj.get("status", {}).get("url")
    return url
