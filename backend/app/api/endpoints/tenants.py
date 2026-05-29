import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ConflictException
from app.models.enums import TenantStatus
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.tenant import (
    AddMemberRequest,
    InvitationResponse,
    InviteMemberRequest,
    QuotaUsageResponse,
    TenantCreateRequest,
    TenantDetailResponse,
    TenantMemberResponse,
    TenantQuotaUpdateRequest,
    TenantResponse,
    TenantStatusRequest,
    TenantUpdateRequest,
    UpdateMemberRoleRequest,
)
from app.services.invitation_service import InvitationService
from app.services.tenant_service import TenantService


def _audit_ctx(request: Request, user: User) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


router = APIRouter(prefix="/tenants", tags=["tenants"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/me", response_model=BaseResponse[TenantResponse])
async def get_my_tenant(
    db: DbDep,
    user: CurrentUser,
) -> BaseResponse[TenantResponse]:
    if user.tenant_id is None:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("未加入任何租户")
    service = TenantService(db)
    tenant = await service.get_tenant(user.tenant_id)
    member_count = await _get_member_count(db, user.tenant_id)
    data = _build_tenant_response(tenant, member_count)
    return BaseResponse(data=data, message="获取成功")


@router.post("", response_model=BaseResponse[TenantResponse])
async def create_tenant(
    req: TenantCreateRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[TenantResponse]:
    service = TenantService(db)
    tenant = await service.create_tenant(req, audit_context=_audit_ctx(request, user))
    data = TenantResponse(
        id=tenant.id,
        name=tenant.name,
        display_name=tenant.display_name,
        description=tenant.description,
        status=tenant.status,
        k8s_namespace_name=tenant.k8s_namespace_name,
        gpu_limit=tenant.gpu_limit,
        cpu_limit=tenant.cpu_limit,
        memory_limit=tenant.memory_limit,
        storage_limit=tenant.storage_limit,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )
    return BaseResponse(data=data, message="租户创建成功")


@router.get("", response_model=PageResponse[TenantResponse])
async def list_tenants(
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
) -> PageResponse[TenantResponse]:
    service = TenantService(db)
    items, total = await service.list_tenants(page=page, page_size=page_size, status=status, keyword=keyword)
    tenant_list = [TenantResponse(**item) for item in items]
    page_data = PageData(items=tenant_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{tenant_id}", response_model=BaseResponse[TenantDetailResponse])
async def get_tenant(
    tenant_id: uuid.UUID,
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[TenantDetailResponse]:
    service = TenantService(db)
    detail = await service.get_tenant_detail(tenant_id)
    return BaseResponse(data=TenantDetailResponse(**detail), message="获取成功")


@router.put("/{tenant_id}", response_model=BaseResponse[TenantResponse])
async def update_tenant(
    tenant_id: uuid.UUID,
    req: TenantUpdateRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[TenantResponse]:
    service = TenantService(db)
    tenant = await service.update_tenant(tenant_id, req, audit_context=_audit_ctx(request, user))
    member_count = await _get_member_count(db, tenant_id)
    data = _build_tenant_response(tenant, member_count)
    return BaseResponse(data=data, message="租户更新成功")


@router.patch("/{tenant_id}/status", response_model=BaseResponse[TenantResponse])
async def toggle_tenant_status(
    tenant_id: uuid.UUID,
    req: TenantStatusRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[TenantResponse]:
    if req.status == TenantStatus.DISABLED and user.tenant_id == tenant_id:
        raise ConflictException("不能禁用自身所属的租户")
    service = TenantService(db)
    tenant = await service.toggle_tenant_status(tenant_id, req.status, audit_context=_audit_ctx(request, user))
    member_count = await _get_member_count(db, tenant_id)
    data = _build_tenant_response(tenant, member_count)
    status_label = "禁用" if req.status == TenantStatus.DISABLED else "恢复"
    return BaseResponse(data=data, message=f"租户{status_label}成功")


@router.delete("/{tenant_id}", response_model=BaseResponse[None])
async def delete_tenant(
    tenant_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[None]:
    service = TenantService(db)
    await service.delete_tenant(tenant_id, audit_context=_audit_ctx(request, user))
    return BaseResponse(message="租户删除成功")


@router.put("/{tenant_id}/quota", response_model=BaseResponse[TenantResponse])
async def update_tenant_quota(
    tenant_id: uuid.UUID,
    req: TenantQuotaUpdateRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[TenantResponse]:
    service = TenantService(db)
    tenant = await service.update_quota(tenant_id, req, audit_context=_audit_ctx(request, user))
    member_count = await _get_member_count(db, tenant_id)
    data = _build_tenant_response(tenant, member_count)
    return BaseResponse(data=data, message="配额更新成功")


@router.get("/{tenant_id}/quota-usage", response_model=BaseResponse[QuotaUsageResponse])
async def get_tenant_quota_usage(
    tenant_id: uuid.UUID,
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("tenants", "read"))],
) -> BaseResponse[QuotaUsageResponse]:
    service = TenantService(db)
    usage = await service.get_quota_usage(tenant_id)
    return BaseResponse(data=QuotaUsageResponse(**usage), message="获取成功")


async def _get_member_count(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    result = await db.execute(select(func.count()).select_from(User).where(User.tenant_id == tenant_id))
    return result.scalar_one()


def _build_tenant_response(tenant: Tenant, member_count: int = 0) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        display_name=tenant.display_name,
        description=tenant.description,
        status=tenant.status,
        k8s_namespace_name=tenant.k8s_namespace_name,
        gpu_limit=tenant.gpu_limit,
        cpu_limit=tenant.cpu_limit,
        memory_limit=tenant.memory_limit,
        storage_limit=tenant.storage_limit,
        member_count=member_count,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


# --- Invitation Endpoints ---


@router.post("/{tenant_id}/invitations", response_model=BaseResponse[InvitationResponse])
async def create_invitation(
    tenant_id: uuid.UUID,
    req: InviteMemberRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[InvitationResponse]:
    service = InvitationService(db)
    invitation = await service.create_invitation(tenant_id, req, user.id, audit_context=_audit_ctx(request, user))
    data = InvitationResponse(
        id=invitation.id,
        tenant_id=invitation.tenant_id,
        email=invitation.email,
        role=invitation.role,
        token=invitation.token,
        status=invitation.status,
        invited_by=invitation.invited_by,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )
    return BaseResponse(data=data, message="邀请创建成功")


@router.get("/{tenant_id}/invitations", response_model=BaseResponse[list[InvitationResponse]])
async def list_invitations(
    tenant_id: uuid.UUID,
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[list[InvitationResponse]]:
    service = InvitationService(db)
    invitations = await service.list_invitations(tenant_id)
    data = [
        InvitationResponse(
            id=inv.id,
            tenant_id=inv.tenant_id,
            email=inv.email,
            role=inv.role,
            token=inv.token,
            status=inv.status,
            invited_by=inv.invited_by,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
        )
        for inv in invitations
    ]
    return BaseResponse(data=data, message="获取成功")


@router.delete("/{tenant_id}/invitations/{invitation_id}", response_model=BaseResponse[None])
async def cancel_invitation(
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[None]:
    service = InvitationService(db)
    await service.cancel_invitation(invitation_id, tenant_id, audit_context=_audit_ctx(request, user))
    return BaseResponse(message="邀请已取消")


# --- Member Endpoints ---


@router.post("/{tenant_id}/members", response_model=BaseResponse[TenantMemberResponse])
async def add_member(
    tenant_id: uuid.UUID,
    req: AddMemberRequest,
    db: DbDep,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[TenantMemberResponse]:
    service = TenantService(db)
    user = await service.add_member(tenant_id, req.user_id, req.role, audit_context=_audit_ctx(request, current_user))
    data = TenantMemberResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        joined_at=user.created_at,
    )
    return BaseResponse(data=data, message="成员添加成功")


@router.get("/{tenant_id}/members", response_model=BaseResponse[list[TenantMemberResponse]])
async def list_members(
    tenant_id: uuid.UUID,
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[list[TenantMemberResponse]]:
    service = TenantService(db)
    members = await service.list_members(tenant_id)
    data = [TenantMemberResponse(**m) for m in members]
    return BaseResponse(data=data, message="获取成功")


@router.patch("/{tenant_id}/members/{user_id}/role", response_model=BaseResponse[TenantMemberResponse])
async def update_member_role(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    req: UpdateMemberRoleRequest,
    db: DbDep,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[TenantMemberResponse]:
    service = TenantService(db)
    user = await service.update_member_role(
        tenant_id, user_id, req.role, current_user.id, audit_context=_audit_ctx(request, current_user)
    )
    data = TenantMemberResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        joined_at=user.created_at,
    )
    return BaseResponse(data=data, message="角色更新成功")


@router.delete("/{tenant_id}/members/{user_id}", response_model=BaseResponse[None])
async def remove_member(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbDep,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[None]:
    service = TenantService(db)
    await service.remove_member(tenant_id, user_id, current_user.id, audit_context=_audit_ctx(request, current_user))
    return BaseResponse(message="成员已移除")
