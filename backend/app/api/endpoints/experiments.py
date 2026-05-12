import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.experiment import ExperimentDetailResponse, ExperimentResponse
from app.services.experiment_service import ExperimentService

router = APIRouter(prefix="/experiments", tags=["experiments"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _require_tenant_id(user: object) -> uuid.UUID:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise ForbiddenException("需要租户上下文才能操作实验")
    return cast("uuid.UUID", tenant_id)


@router.get("", response_model=PageResponse[ExperimentResponse])
async def list_experiments(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("experiments", "read"))],
    training_job_name: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[ExperimentResponse]:
    service = ExperimentService(db)
    tenant_id = _require_tenant_id(user)
    items, total = await service.get_experiments(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        training_job_name=training_job_name,
        status=status,
    )
    experiment_list = [ExperimentResponse(**item) for item in items]
    page_data = PageData(items=experiment_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{experiment_id}", response_model=BaseResponse[ExperimentDetailResponse])
async def get_experiment(
    experiment_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("experiments", "read"))],
) -> BaseResponse[ExperimentDetailResponse]:
    service = ExperimentService(db)
    tenant_id = _require_tenant_id(user)
    item = await service.get_experiment_detail(experiment_id, tenant_id)
    if not item:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("实验记录不存在")
    return BaseResponse(data=ExperimentDetailResponse(**item), message="获取成功")
