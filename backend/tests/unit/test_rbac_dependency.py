import pytest

from app.api.deps import require_permission
from app.core.casbin import CasbinEnforcer
from app.core.config import settings
from app.core.exceptions import ForbiddenException
from app.models.enums import UserRole


class MockUser:
    def __init__(self, role: UserRole):
        self.role = role
        self.id = "test-id"
        self.username = "test"
        self.email = "test@example.com"
        self.is_active = True


@pytest.fixture(scope="module", autouse=True)
def init_casbin():
    CasbinEnforcer.initialize(settings.DATABASE_URL)


@pytest.mark.parametrize(
    "role,resource,action,expected",
    [
        (UserRole.ANNOTATOR, "training_jobs", "write", False),
        (UserRole.ANNOTATOR, "training_jobs", "read", False),
        (UserRole.ANNOTATOR, "annotations", "write", True),
        (UserRole.ANNOTATOR, "annotations", "read", True),
        (UserRole.ANNOTATOR, "datasets", "read", True),
        (UserRole.ENGINEER, "training_jobs", "write", True),
        (UserRole.ENGINEER, "training_jobs", "read", True),
        (UserRole.ENGINEER, "inference_services", "read", True),
        (UserRole.ENGINEER, "inference_services", "write", False),
        (UserRole.ENGINEER, "models", "read", True),
        (UserRole.ENGINEER, "models", "write", False),
        (UserRole.ENGINEER, "users", "read", False),
        (UserRole.MLOPS, "inference_services", "manage", True),
        (UserRole.MLOPS, "inference_services", "read", True),
        (UserRole.MLOPS, "training_jobs", "manage", True),
        (UserRole.MLOPS, "training_jobs", "write", True),
        (UserRole.MLOPS, "training_jobs", "read", True),
        (UserRole.MLOPS, "users", "read", True),
        (UserRole.MLOPS, "users", "manage", False),
        (UserRole.MLOPS, "tenants", "manage", False),
        (UserRole.ADMIN, "users", "manage", True),
        (UserRole.ADMIN, "users", "read", True),
        (UserRole.ADMIN, "tenants", "manage", True),
        (UserRole.ADMIN, "training_jobs", "write", True),
        (UserRole.ADMIN, "training_jobs", "read", True),
        (UserRole.ADMIN, "monitoring", "manage", True),
    ],
)
@pytest.mark.asyncio
async def test_rbac_permission_check(role, resource, action, expected):
    checker = require_permission(resource, action)
    user = MockUser(role)

    if expected:
        result = await checker(user)
        assert result is user
    else:
        with pytest.raises(ForbiddenException):
            await checker(user)
