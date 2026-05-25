from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import BadRequestException
from app.models.enums import UserRole
from app.schemas.base import BaseResponse
from app.schemas.dashboard import (
    AdminDashboard,
    AnnotatorDashboard,
    DashboardResponse,
    EngineerDashboard,
    MLOpsDashboard,
)
from app.services.dashboard_service import DashboardService

DashboardData = EngineerDashboard | AdminDashboard | AnnotatorDashboard | MLOpsDashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=BaseResponse[DashboardResponse])
async def get_dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("dashboard", "read"))],
) -> BaseResponse[DashboardResponse]:
    service = DashboardService(db)
    role = user.role
    role_str = role.value
    user_id = user.id
    tenant_id = user.tenant_id

    dashboard_data: DashboardData
    if role == UserRole.ADMIN:
        raw = await service.get_admin_dashboard(user_id)
        dashboard_data = AdminDashboard(**raw["data"])
    elif role == UserRole.MLOPS:
        if not tenant_id:
            raise BadRequestException("当前用户未关联租户")
        raw = await service.get_mlops_dashboard(user_id, tenant_id)
        dashboard_data = MLOpsDashboard(**raw["data"])
    elif role == UserRole.ANNOTATOR:
        if not tenant_id:
            raise BadRequestException("当前用户未关联租户")
        raw = await service.get_annotator_dashboard(user_id, tenant_id)
        dashboard_data = AnnotatorDashboard(**raw["data"])
    else:
        if not tenant_id:
            raise BadRequestException("当前用户未关联租户")
        raw = await service.get_engineer_dashboard(user_id, tenant_id)
        dashboard_data = EngineerDashboard(**raw["data"])

    return BaseResponse(data=DashboardResponse(role=role_str, data=dashboard_data))
