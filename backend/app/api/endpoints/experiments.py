import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.experiment import (
    CompareRequest,
    ExperimentComparisonResponse,
    ExperimentDetailResponse,
    ExperimentResponse,
    MetricHistoryPoint,
)
from app.services.experiment_service import ExperimentService

router = APIRouter(prefix="/experiments", tags=["experiments"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_sort_by_query = Query(None)
_sort_order_query = Query(None)
_dataset_id_query = Query(None)
_image_id_query = Query(None)
_start_date_query = Query(None)
_end_date_query = Query(None)


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
    sort_by: str | None = _sort_by_query,
    sort_order: str | None = _sort_order_query,
    dataset_id: uuid.UUID | None = _dataset_id_query,
    image_id: uuid.UUID | None = _image_id_query,
    start_date: str | None = _start_date_query,
    end_date: str | None = _end_date_query,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[ExperimentResponse]:
    service = ExperimentService(db)
    tenant_id = _require_tenant_id(user)

    from datetime import datetime

    parsed_start = datetime.fromisoformat(start_date) if start_date else None
    parsed_end = datetime.fromisoformat(end_date) if end_date else None

    items, total = await service.get_experiments(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        training_job_name=training_job_name,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        dataset_id=dataset_id,
        image_id=image_id,
        start_date=parsed_start,
        end_date=parsed_end,
    )
    experiment_list = [ExperimentResponse(**item) for item in items]
    page_data = PageData(items=experiment_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.post("/compare", response_model=BaseResponse[ExperimentComparisonResponse])
async def compare_experiments(
    body: CompareRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("experiments", "read"))],
) -> BaseResponse[ExperimentComparisonResponse]:
    service = ExperimentService(db)
    tenant_id = _require_tenant_id(user)
    result = await service.compare_experiments(tenant_id, body.experiment_ids)
    if not result:
        from app.core.exceptions import BadRequestException

        raise BadRequestException("至少需要 2 个有效实验才能进行对比")
    return BaseResponse(data=ExperimentComparisonResponse(**result), message="获取成功")


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


@router.get("/{experiment_id}/metrics/{metric_key}/history", response_model=BaseResponse[list[MetricHistoryPoint]])
async def get_metric_history(
    experiment_id: uuid.UUID,
    metric_key: str,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("experiments", "read"))],
) -> BaseResponse[list[MetricHistoryPoint]]:
    service = ExperimentService(db)
    tenant_id = _require_tenant_id(user)
    points = await service.get_metric_history(experiment_id, tenant_id, metric_key)
    return BaseResponse(data=[MetricHistoryPoint(**p) for p in points], message="获取成功")
