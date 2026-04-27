from fastapi import APIRouter

from app.schemas.base import BaseResponse

api_router = APIRouter()


@api_router.get("/health", response_model=BaseResponse)
async def health_check() -> BaseResponse:
    return BaseResponse(data={"status": "healthy"})
