import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.tenant import Tenant
from app.schemas.base import BaseResponse
from app.schemas.credential import CredentialCreateRequest, CredentialResponse
from app.services.credential_service import CredentialService

router = APIRouter(prefix="/credentials", tags=["credentials"])

_credential_service = CredentialService()
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _get_tenant_name(db: AsyncSession, tenant_id: uuid.UUID) -> str:
    result = await db.execute(select(Tenant.name).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise NotFoundException("租户不存在")
    return tenant


@router.post("", response_model=BaseResponse[CredentialResponse])
async def create_credential(
    req: CredentialCreateRequest,
    db: DbDep,
    current_user: CurrentUser,
) -> BaseResponse[CredentialResponse]:
    if not current_user.tenant_id:
        raise ForbiddenException("无租户的用户无法创建凭证")

    tenant_name = await _get_tenant_name(db, current_user.tenant_id)
    _credential_service.store_credential(tenant_name, req.name, req.data)

    return BaseResponse(
        data=CredentialResponse(
            name=req.name,
            type=req.type,
            created_at=datetime.now(UTC),
        ),
        message="凭证创建成功",
    )


@router.get("", response_model=BaseResponse[list[CredentialResponse]])
async def list_credentials(
    current_user: CurrentUser,
) -> BaseResponse[list[CredentialResponse]]:
    if not current_user.tenant_id:
        raise ForbiddenException("无租户的用户无法查看凭证")

    return BaseResponse(data=[], message="获取成功")


@router.delete("/{credential_id}", response_model=BaseResponse[None])
async def delete_credential(
    credential_id: str,
    db: DbDep,
    current_user: CurrentUser,
) -> BaseResponse[None]:
    if not current_user.tenant_id:
        raise ForbiddenException("无租户的用户无法删除凭证")

    tenant_name = await _get_tenant_name(db, current_user.tenant_id)
    _credential_service.delete_credential(tenant_name, credential_id)
    return BaseResponse(message="凭证删除成功")
