from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException
from app.schemas.base import BaseResponse


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    response: BaseResponse[None] = BaseResponse(success=False, message=exc.message, data=None)
    return JSONResponse(status_code=exc.status_code, content=response.model_dump())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    response: BaseResponse[None] = BaseResponse(success=False, message="服务内部错误", data=None)
    return JSONResponse(status_code=500, content=response.model_dump())
