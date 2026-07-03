import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException
from app.schemas.base import BaseResponse

logger = structlog.get_logger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    response: BaseResponse[None] = BaseResponse(success=False, message=exc.message, data=None)
    return JSONResponse(status_code=exc.status_code, content=response.model_dump())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """记录完整异常并通过响应暴露摘要, 避免前后端无法定位未预期的错误."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled_exception", method=request.method, path=request.url.path)
    detail = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
    message = f"服务内部错误: {detail}"
    if request_id:
        message += f" (request_id: {request_id})"
    response: BaseResponse[None] = BaseResponse(success=False, message=message, data=None)
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(status_code=500, content=response.model_dump(), headers=headers)
