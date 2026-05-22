import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, ResourceType, UserRole
from app.models.user import User
from app.schemas.audit import AuditLogQueryParams
from app.services.audit_service import AuditService


def _make_user(role=UserRole.ADMIN, tenant_id=None):
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = role
    user.tenant_id = tenant_id
    return user


def _make_audit_log(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "action": AuditAction.CREATE,
        "resource_type": ResourceType.TENANT,
        "resource_id": str(uuid.uuid4()),
        "detail": {"name": "test"},
        "ip_address": "127.0.0.1",
        "user_agent": "test-agent",
        "request_id": "abc123",
    }
    defaults.update(overrides)

    log = MagicMock(spec=AuditLog)
    for k, v in defaults.items():
        setattr(log, k, v)
    return log


def _row_result(rows):
    """Simulate result.all() returning list of (AuditLog, username) tuples."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _one_or_none_row(log, username):
    """Simulate result.one_or_none() returning a single (AuditLog, username) row."""
    result = MagicMock()
    result.one_or_none.return_value = (log, username)
    return result


def _scalar_one_result(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _scalar_one_or_none_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def audit_service(mock_db):
    return AuditService(mock_db)


class TestLogAction:
    async def test_log_action_with_user(self, audit_service, mock_db):
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        await audit_service.log_action(
            action=AuditAction.CREATE,
            resource_type=ResourceType.TENANT,
            ip_address="127.0.0.1",
            user_id=user_id,
            tenant_id=tenant_id,
            resource_id=str(tenant_id),
            detail={"name": "test"},
            user_agent="test-agent",
            request_id="req123",
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_log_action_system_no_user(self, audit_service, mock_db):
        await audit_service.log_action(
            action=AuditAction.LOGIN,
            resource_type=ResourceType.USER,
            ip_address="10.0.0.1",
            detail={"success": False, "reason": "user_not_found"},
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()


class TestQueryLogs:
    async def test_admin_sees_all(self, audit_service, mock_db):
        admin = _make_user(role=UserRole.ADMIN)
        log1, log2 = _make_audit_log(), _make_audit_log()
        rows = [(log1, "user1"), (log2, "user2")]

        mock_db.execute.side_effect = [
            _scalar_one_result(2),
            _row_result(rows),
        ]

        params = AuditLogQueryParams(page=1, page_size=20)
        items, total = await audit_service.query_logs(params, admin)

        assert total == 2
        assert len(items) == 2
        assert items[0] == (log1, "user1")

    async def test_mlops_sees_own_tenant_only(self, audit_service, mock_db):
        tenant_id = uuid.uuid4()
        mlops = _make_user(role=UserRole.MLOPS, tenant_id=tenant_id)

        mock_db.execute.side_effect = [
            _scalar_one_result(0),
            _row_result([]),
        ]

        params = AuditLogQueryParams(page=1, page_size=20)
        items, total = await audit_service.query_logs(params, mlops)

        assert total == 0
        assert items == []

    async def test_filter_by_action(self, audit_service, mock_db):
        admin = _make_user(role=UserRole.ADMIN)
        log = _make_audit_log()

        mock_db.execute.side_effect = [
            _scalar_one_result(1),
            _row_result([(log, "admin")]),
        ]

        params = AuditLogQueryParams(action=[AuditAction.CREATE], page=1, page_size=20)
        _items, total = await audit_service.query_logs(params, admin)

        assert total == 1

    async def test_filter_by_time_range(self, audit_service, mock_db):
        admin = _make_user(role=UserRole.ADMIN)

        mock_db.execute.side_effect = [
            _scalar_one_result(0),
            _row_result([]),
        ]

        from datetime import datetime

        params = AuditLogQueryParams(
            start_time=datetime(2026, 1, 1),
            end_time=datetime(2026, 12, 31),
            page=1,
            page_size=20,
        )
        _items, total = await audit_service.query_logs(params, admin)
        assert total == 0

    async def test_other_role_forbidden(self, audit_service, mock_db):
        engineer = _make_user(role=UserRole.ENGINEER)
        params = AuditLogQueryParams(page=1, page_size=20)

        with pytest.raises(ForbiddenException):
            await audit_service.query_logs(params, engineer)


class TestGetLog:
    async def test_admin_get_any_log(self, audit_service, mock_db):
        admin = _make_user(role=UserRole.ADMIN)
        log = _make_audit_log()

        mock_db.execute.return_value = _one_or_none_row(log, "testuser")

        result_log, username = await audit_service.get_log(log.id, admin)
        assert result_log == log
        assert username == "testuser"

    async def test_mlops_get_own_tenant_log(self, audit_service, mock_db):
        tenant_id = uuid.uuid4()
        mlops = _make_user(role=UserRole.MLOPS, tenant_id=tenant_id)
        log = _make_audit_log(tenant_id=tenant_id)

        mock_db.execute.return_value = _one_or_none_row(log, "mlops_user")

        result_log, _username = await audit_service.get_log(log.id, mlops)
        assert result_log == log

    async def test_mlops_cannot_see_other_tenant(self, audit_service, mock_db):
        mlops = _make_user(role=UserRole.MLOPS, tenant_id=uuid.uuid4())
        log = _make_audit_log(tenant_id=uuid.uuid4())

        mock_db.execute.return_value = _one_or_none_row(log, "other")

        with pytest.raises(ForbiddenException):
            await audit_service.get_log(log.id, mlops)

    async def test_log_not_found(self, audit_service, mock_db):
        admin = _make_user(role=UserRole.ADMIN)

        result = MagicMock()
        result.one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(NotFoundException):
            await audit_service.get_log(uuid.uuid4(), admin)


class TestImmutability:
    def test_no_update_method(self):
        assert not hasattr(AuditService, "update_log")

    def test_no_delete_method(self):
        assert not hasattr(AuditService, "delete_log")
