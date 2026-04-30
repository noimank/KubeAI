from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models.enums import AuditAction, InvitationStatus, ResourceType, UserRole
from app.models.invitation import TenantInvitation
from app.models.tenant import Tenant
from app.models.user import User
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.tenant import InviteMemberRequest

logger = logging.getLogger(__name__)

_ADMIN_ROLES = {UserRole.ADMIN}


class InvitationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_invitation(
        self,
        tenant_id: uuid.UUID,
        req: InviteMemberRequest,
        inviter_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> TenantInvitation:
        if req.role in _ADMIN_ROLES:
            raise BadRequestException("不能邀请管理员角色")

        # 验证租户存在
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        if result.scalar_one_or_none() is None:
            raise NotFoundException("租户不存在")

        # 校验邮箱是否已是该租户成员
        existing_member = await self.db.execute(
            select(User).where(User.email == req.email, User.tenant_id == tenant_id)
        )
        if existing_member.scalar_one_or_none() is not None:
            raise ConflictException("该邮箱已是本租户成员")

        # 校验是否有 pending 邀请
        existing_inv = await self.db.execute(
            select(TenantInvitation).where(
                TenantInvitation.tenant_id == tenant_id,
                TenantInvitation.email == req.email,
                TenantInvitation.status == InvitationStatus.PENDING,
            )
        )
        if existing_inv.scalar_one_or_none() is not None:
            raise ConflictException("该邮箱已有待处理的邀请")

        invitation = TenantInvitation(
            tenant_id=tenant_id,
            email=req.email,
            role=req.role,
            invited_by=inviter_id,
        )
        self.db.add(invitation)
        await self.db.flush()
        await self.db.refresh(invitation)

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.INVITE,
                resource_type=ResourceType.INVITATION,
                resource_id=str(invitation.id),
                detail={"email": req.email, "role": req.role.value},
                tenant_id=tenant_id,
                **audit_context,
            )

        return invitation

    async def list_invitations(self, tenant_id: uuid.UUID) -> list[TenantInvitation]:
        result = await self.db.execute(
            select(TenantInvitation)
            .where(
                TenantInvitation.tenant_id == tenant_id,
                TenantInvitation.status != InvitationStatus.EXPIRED,
            )
            .order_by(TenantInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def cancel_invitation(
        self, invitation_id: uuid.UUID, tenant_id: uuid.UUID, audit_context: dict[str, Any] | None = None
    ) -> None:
        result = await self.db.execute(
            select(TenantInvitation).where(
                TenantInvitation.id == invitation_id,
                TenantInvitation.tenant_id == tenant_id,
            )
        )
        invitation = result.scalar_one_or_none()
        if not invitation:
            raise NotFoundException("邀请不存在")
        if invitation.status != InvitationStatus.PENDING:
            raise BadRequestException("只能取消待处理的邀请")
        invitation.status = InvitationStatus.CANCELLED
        await self.db.flush()

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.CANCEL_INVITE,
                resource_type=ResourceType.INVITATION,
                resource_id=str(invitation.id),
                detail={"email": invitation.email, "role": invitation.role.value},
                tenant_id=tenant_id,
                **audit_context,
            )

    async def get_invitation_by_token(self, token: str) -> TenantInvitation | None:
        result = await self.db.execute(select(TenantInvitation).where(TenantInvitation.token == token))
        invitation = result.scalar_one_or_none()
        if not invitation:
            return None
        if invitation.status != InvitationStatus.PENDING:
            return None
        if invitation.expires_at < datetime.now(UTC):
            return None
        return invitation

    async def get_invitation_info(self, token: str) -> dict[str, Any]:
        invitation = await self.get_invitation_by_token(token)
        if not invitation:
            raise BadRequestException("邀请无效或已过期")

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.id == invitation.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在")

        return {
            "tenant_name": tenant.name,
            "tenant_display_name": tenant.display_name,
            "email": invitation.email,
            "role": invitation.role,
        }

    async def accept_invitation(self, token: str, user_id: uuid.UUID | None = None) -> User | None:
        invitation = await self.get_invitation_by_token(token)
        if not invitation:
            raise BadRequestException("邀请无效或已过期")

        if user_id:
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise NotFoundException("用户不存在")
            user.tenant_id = invitation.tenant_id
            user.role = invitation.role

        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_by = user_id
        await self.db.flush()
        if user_id:
            await self.db.refresh(user)
            return user
        return None
