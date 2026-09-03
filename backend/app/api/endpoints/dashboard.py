from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.schemas.base import BaseResponse
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=BaseResponse[DashboardResponse])
async def get_dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("dashboard", "read"))],
) -> BaseResponse[DashboardResponse]:
    data = await DashboardService(db).get_dashboard(user)
    return BaseResponse(data=DashboardResponse(**data))
