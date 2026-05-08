from fastapi import APIRouter

from app.api.endpoints.audit_logs import router as audit_logs_router
from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.credentials import router as credentials_router
from app.api.endpoints.datasets import router as datasets_router
from app.api.endpoints.images import router as images_router
from app.api.endpoints.tenants import router as tenants_router
from app.api.endpoints.training_jobs import router as training_jobs_router
from app.api.endpoints.users import router as users_router
from app.schemas.base import BaseResponse

HealthResponse = BaseResponse[dict[str, str]]

api_router = APIRouter()


@api_router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return BaseResponse(data={"status": "healthy"})


api_router.include_router(auth_router)
api_router.include_router(credentials_router)
api_router.include_router(datasets_router)
api_router.include_router(images_router)
api_router.include_router(tenants_router)
api_router.include_router(training_jobs_router)
api_router.include_router(users_router)
api_router.include_router(audit_logs_router)
