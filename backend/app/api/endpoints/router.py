from fastapi import APIRouter

from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.credentials import router as credentials_router
from app.api.endpoints.tenants import router as tenants_router
from app.schemas.base import BaseResponse

HealthResponse = BaseResponse[dict[str, str]]

api_router = APIRouter()


@api_router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return BaseResponse(data={"status": "healthy"})


api_router.include_router(auth_router)
api_router.include_router(credentials_router)
api_router.include_router(tenants_router)
