import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models.enums import InvitationStatus, UserRole
from app.models.invitation import TenantInvitation
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import InviteMemberRequest
from app.services.invitation_service import InvitationService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_tenant():
    t = Tenant(name="test-tenant", display_name="Test Tenant")
    t.id = uuid.uuid4()
    return t


def _make_invitation(tenant_id=None, email="user@example.com", role=UserRole.ENGINEER):
    inv = TenantInvitation(
        tenant_id=tenant_id or uuid.uuid4(),
        email=email,
        role=role,
        invited_by=uuid.uuid4(),
    )
    inv.token = "test-token-123"
    return inv


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return InvitationService(mock_db)


class TestCreateInvitation:
    async def test_create_invitation_success(self, service, mock_db):
        tenant = _make_tenant()
        tenant_result = _sync_result(tenant)
        member_result = _sync_result(None)
        inv_result = _sync_result(None)

        mock_db.execute.side_effect = [tenant_result, member_result, inv_result]

        req = InviteMemberRequest(email="user@example.com", role=UserRole.ENGINEER)
        result = await service.create_invitation(tenant.id, req, uuid.uuid4())

        assert result is not None
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_create_invitation_admin_role_rejected(self, service, mock_db):
        req = InviteMemberRequest(email="user@example.com", role=UserRole.ADMIN)
        with pytest.raises(BadRequestException, match="不能邀请管理员角色"):
            await service.create_invitation(uuid.uuid4(), req, uuid.uuid4())

    async def test_create_invitation_tenant_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        req = InviteMemberRequest(email="user@example.com", role=UserRole.ENGINEER)
        with pytest.raises(NotFoundException, match="租户不存在"):
            await service.create_invitation(uuid.uuid4(), req, uuid.uuid4())

    async def test_create_invitation_email_already_member(self, service, mock_db):
        tenant = _make_tenant()
        existing_user = User(
            username="existing",
            email="user@example.com",
            hashed_password="fake_hash",
        )
        mock_db.execute.side_effect = [_sync_result(tenant), _sync_result(existing_user)]

        req = InviteMemberRequest(email="user@example.com", role=UserRole.ENGINEER)
        with pytest.raises(ConflictException, match="该邮箱已是本租户成员"):
            await service.create_invitation(tenant.id, req, uuid.uuid4())

    async def test_create_invitation_duplicate_pending(self, service, mock_db):
        tenant = _make_tenant()
        existing_inv = _make_invitation()

        mock_db.execute.side_effect = [
            _sync_result(tenant),
            _sync_result(None),
            _sync_result(existing_inv),
        ]

        req = InviteMemberRequest(email="user@example.com", role=UserRole.ENGINEER)
        with pytest.raises(ConflictException, match="该邮箱已有待处理的邀请"):
            await service.create_invitation(tenant.id, req, uuid.uuid4())


class TestListInvitations:
    async def test_list_invitations(self, service, mock_db):
        inv = _make_invitation()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [inv]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await service.list_invitations(inv.tenant_id)
        assert len(result) == 1
        assert result[0].email == "user@example.com"


class TestCancelInvitation:
    async def test_cancel_invitation_success(self, service, mock_db):
        inv = _make_invitation()
        mock_db.execute.return_value = _sync_result(inv)

        await service.cancel_invitation(inv.id, inv.tenant_id)
        assert inv.status == InvitationStatus.CANCELLED
        mock_db.flush.assert_called_once()

    async def test_cancel_invitation_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)
        with pytest.raises(NotFoundException, match="邀请不存在"):
            await service.cancel_invitation(uuid.uuid4(), uuid.uuid4())

    async def test_cancel_invitation_already_accepted(self, service, mock_db):
        inv = _make_invitation()
        inv.status = InvitationStatus.ACCEPTED
        mock_db.execute.return_value = _sync_result(inv)

        with pytest.raises(BadRequestException, match="只能取消待处理的邀请"):
            await service.cancel_invitation(inv.id, inv.tenant_id)


class TestGetInvitationByToken:
    async def test_get_valid_invitation(self, service, mock_db):
        inv = _make_invitation()
        mock_db.execute.return_value = _sync_result(inv)

        result = await service.get_invitation_by_token("test-token-123")
        assert result is not None
        assert result.token == "test-token-123"

    async def test_get_invitation_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        result = await service.get_invitation_by_token("invalid-token")
        assert result is None

    async def test_get_invitation_already_accepted(self, service, mock_db):
        inv = _make_invitation()
        inv.status = InvitationStatus.ACCEPTED
        mock_db.execute.return_value = _sync_result(inv)

        result = await service.get_invitation_by_token("test-token-123")
        assert result is None

    async def test_get_invitation_expired(self, service, mock_db):
        inv = _make_invitation()
        inv.expires_at = datetime.now(UTC) - timedelta(days=1)
        mock_db.execute.return_value = _sync_result(inv)

        result = await service.get_invitation_by_token("test-token-123")
        assert result is None


class TestAcceptInvitation:
    async def test_accept_invitation_success(self, service, mock_db):
        inv = _make_invitation()
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="fake_hash",
        )
        user.tenant_id = None
        user.role = UserRole.ENGINEER

        mock_db.execute.side_effect = [
            _sync_result(inv),  # get_invitation_by_token
            _sync_result(user),  # select User
        ]
        mock_db.refresh = AsyncMock()

        await service.accept_invitation("test-token-123", user_id=user.id)
        assert inv.status == InvitationStatus.ACCEPTED
        mock_db.flush.assert_called_once()

    async def test_accept_invitation_invalid_token(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(BadRequestException, match="邀请无效或已过期"):
            await service.accept_invitation("invalid-token", user_id=uuid.uuid4())
