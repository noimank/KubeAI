import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.models.tuning import TuningStudy
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.tuning import (
    BestTrialResponse,
    TuningInsightsResponse,
    TuningStudyCreateRequest,
    TuningStudyResponse,
    TuningTrialResponse,
)
from app.services.tuning_service import TuningService
from app.tasks.tuning_tasks import enqueue_drive_study

router = APIRouter(prefix="/tuning", tags=["tuning"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _require_tenant_id(user: object) -> uuid.UUID:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise ForbiddenException("需要租户上下文才能操作调优任务")
    return cast("uuid.UUID", tenant_id)


def _study_to_response(study: TuningStudy, progress: dict[str, int] | None = None) -> TuningStudyResponse:
    resp = TuningStudyResponse.model_validate(study)
    if progress:
        resp.trial_count = progress["trial_count"]
        resp.finalized_count = progress["finalized_count"]
        resp.running_count = progress["running_count"]
    return resp


@router.post("/studies", response_model=BaseResponse[TuningStudyResponse])
async def create_tuning_study(
    req: TuningStudyCreateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("tuning", "write"))],
) -> BaseResponse[TuningStudyResponse]:
    service = TuningService(db)
    tenant_id = _require_tenant_id(user)
    study = await service.create_study(req, tenant_id=tenant_id, user_id=user.id)
    # 立即驱动一次, 让首个 trial 尽快启动 (兜底 cron 随后按固定周期驱动)
    await enqueue_drive_study(study.id)
    return BaseResponse(data=_study_to_response(study), message="调优任务创建成功")


@router.get("/studies", response_model=PageResponse[TuningStudyResponse])
async def list_tuning_studies(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("tuning", "read"))],
    status: str | None = Query(None),
    name: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[TuningStudyResponse]:
    service = TuningService(db)
    tenant_id = _require_tenant_id(user)
    items, total = await service.list_studies(
        tenant_id=tenant_id, page=page, page_size=page_size, status=status, name=name
    )
    progress_map = await service.get_progress_map([s.id for s in items])
    study_list = [_study_to_response(s, progress_map.get(s.id)) for s in items]
    return PageResponse(
        data=PageData(items=study_list, total=total, page=page, page_size=page_size), message="获取成功"
    )


@router.get("/studies/{study_id}", response_model=BaseResponse[TuningStudyResponse])
async def get_tuning_study(
    study_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("tuning", "read"))],
) -> BaseResponse[TuningStudyResponse]:
    service = TuningService(db)
    tenant_id = _require_tenant_id(user)
    study = await service.get_study(study_id, tenant_id)
    progress = await service.get_progress(study_id)
    return BaseResponse(data=_study_to_response(study, progress), message="获取成功")


@router.get("/studies/{study_id}/trials", response_model=BaseResponse[list[TuningTrialResponse]])
async def list_tuning_trials(
    study_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("tuning", "read"))],
) -> BaseResponse[list[TuningTrialResponse]]:
    service = TuningService(db)
    tenant_id = _require_tenant_id(user)
    items = await service.list_trials(study_id, tenant_id)
    trials = [TuningTrialResponse(**item) for item in items]
    return BaseResponse(data=trials, message="获取成功")


@router.get("/studies/{study_id}/best", response_model=BaseResponse[BestTrialResponse])
async def get_best_trial(
    study_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("tuning", "read"))],
) -> BaseResponse[BestTrialResponse]:
    service = TuningService(db)
    tenant_id = _require_tenant_id(user)
    data = await service.get_best_trial(study_id, tenant_id)
    return BaseResponse(data=BestTrialResponse(**data), message="获取成功")


@router.get("/studies/{study_id}/insights", response_model=BaseResponse[TuningInsightsResponse])
async def get_tuning_insights(
    study_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("tuning", "read"))],
) -> BaseResponse[TuningInsightsResponse]:
    service = TuningService(db)
    tenant_id = _require_tenant_id(user)
    data = await service.get_insights(study_id, tenant_id)
    return BaseResponse(data=TuningInsightsResponse(**data), message="获取成功")


@router.post("/studies/{study_id}/stop", response_model=BaseResponse[TuningStudyResponse])
async def stop_tuning_study(
    study_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("tuning", "write"))],
) -> BaseResponse[TuningStudyResponse]:
    service = TuningService(db)
    tenant_id = _require_tenant_id(user)
    study = await service.stop_study(study_id, tenant_id)
    progress = await service.get_progress(study_id)
    return BaseResponse(data=_study_to_response(study, progress), message="调优任务已停止")


@router.delete("/studies/{study_id}", response_model=BaseResponse[None])
async def delete_tuning_study(
    study_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("tuning", "manage"))],
) -> BaseResponse[None]:
    service = TuningService(db)
    tenant_id = _require_tenant_id(user)
    await service.delete_study(study_id, tenant_id)
    return BaseResponse(message="调优任务已删除")
