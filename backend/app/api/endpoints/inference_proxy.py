import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import UnauthorizedException
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

    target_url = f"{svc.endpoint_url}/{path}"

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
        )
        await db.commit()
    except Exception:
        logger.warning("Failed to write audit log for proxy request", exc_info=True)

    excluded_headers = {"transfer-encoding", "content-encoding", "content-length"}
    response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers,
        media_type=resp.headers.get("Content-Type"),
    )
