from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.exceptions import ForbiddenException
from app.schemas.base import BaseResponse
from app.schemas.credential import CredentialCreateRequest, CredentialResponse
from app.services.credential_service import CredentialService

router = APIRouter(prefix="/credentials", tags=["credentials"])

_credential_service = CredentialService()


@router.post("", response_model=BaseResponse[CredentialResponse])
async def create_credential(
    req: CredentialCreateRequest,
    current_user: CurrentUser,
) -> BaseResponse[CredentialResponse]:
    if not current_user.tenant_id:
        raise ForbiddenException("无租户的用户无法创建凭证")

    _credential_service.store_credential(current_user.tenant_id, req.name, req.data)

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
    current_user: CurrentUser,
) -> BaseResponse[None]:
    if not current_user.tenant_id:
        raise ForbiddenException("无租户的用户无法删除凭证")

    _credential_service.delete_credential(current_user.tenant_id, credential_id)
    return BaseResponse(message="凭证删除成功")
