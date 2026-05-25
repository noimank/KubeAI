from fastapi import APIRouter

from app.api.endpoints.annotations import router as annotations_router
from app.api.endpoints.audit_logs import router as audit_logs_router
from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.credentials import router as credentials_router
from app.api.endpoints.datasets import router as datasets_router
from app.api.endpoints.dev_environment_images import router as dev_environment_images_router
from app.api.endpoints.dev_environments import router as dev_environments_router
from app.api.endpoints.experiments import router as experiments_router
from app.api.endpoints.images import router as images_router
from app.api.endpoints.inference_proxy import router as inference_proxy_router
from app.api.endpoints.inference_services import router as inference_services_router
from app.api.endpoints.model_registry import router as model_registry_router
from app.api.endpoints.monitoring import router as monitoring_router
from app.api.endpoints.notifications import router as notifications_router
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
api_router.include_router(annotations_router)
api_router.include_router(credentials_router)
api_router.include_router(datasets_router)
api_router.include_router(dev_environments_router)
api_router.include_router(dev_environment_images_router)
api_router.include_router(experiments_router)
api_router.include_router(images_router)
api_router.include_router(inference_services_router)
api_router.include_router(inference_proxy_router)
api_router.include_router(model_registry_router)
api_router.include_router(monitoring_router)
api_router.include_router(notifications_router)
api_router.include_router(tenants_router)
api_router.include_router(training_jobs_router)
api_router.include_router(users_router)
api_router.include_router(audit_logs_router)
