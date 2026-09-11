from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ExternalServiceException
from app.models.enums import UserRole
from app.models.user import User
from app.services.casdoor_service import sync_role_to_casdoor


class FakeCasdoorClient:
    def __init__(self, roles, users=None):
        self.roles = roles
        self.updates = []
        self.fetch_count = 0
        self.users = users or {}

    async def get_kubeai_roles(self):
        self.fetch_count += 1
        return self.roles

    async def get_user_by_ref(self, ref):
        return self.users.get(ref)

    async def update_role(self, role):
        self.updates.append(role["name"])


UUID = "b4758e0d-d2db-4fa2-8040-a383d318491e"


def _make_oidc_user(external_id="kubeai/alice"):
    user = MagicMock(spec=User)
    user.auth_provider = "oidc"
    user.external_id = external_id
    return user


class TestSyncRoleToCasdoor:
    async def test_local_user_skipped(self):
        user = _make_oidc_user()
        user.auth_provider = "local"
        client = FakeCasdoorClient(roles=[{"name": "kubeai_mlops", "users": []}])

        await sync_role_to_casdoor(user, UserRole.MLOPS, client=client)

        assert client.fetch_count == 0

    async def test_missing_external_id_skipped(self):
        user = _make_oidc_user(external_id=None)
        client = FakeCasdoorClient(roles=[{"name": "kubeai_mlops", "users": []}])

        await sync_role_to_casdoor(user, UserRole.MLOPS, client=client)

        assert client.fetch_count == 0

    async def test_role_switch_moves_user_between_roles(self):
        user = _make_oidc_user()
        client = FakeCasdoorClient(
            roles=[
                {"name": "kubeai_engineer", "users": ["kubeai/alice", "kubeai/bob"]},
                {"name": "kubeai_mlops", "users": ["kubeai/bob"]},
                {"name": "kubeai_admin", "users": []},
                {"name": "kubeai_annotator", "users": []},
            ]
        )

        await sync_role_to_casdoor(user, UserRole.MLOPS, client=client)

        assert client.updates == ["kubeai_engineer", "kubeai_mlops"]
        by_name = {r["name"]: r["users"] for r in client.roles}
        assert by_name["kubeai_engineer"] == ["kubeai/bob"]
        assert by_name["kubeai_mlops"] == ["kubeai/bob", "kubeai/alice"]
        assert by_name["kubeai_admin"] == []
        assert by_name["kubeai_annotator"] == []

    async def test_user_without_existing_role_added(self):
        user = _make_oidc_user()
        client = FakeCasdoorClient(
            roles=[
                {"name": "kubeai_mlops", "users": []},
                {"name": "kubeai_admin", "users": []},
            ]
        )

        await sync_role_to_casdoor(user, UserRole.MLOPS, client=client)

        assert client.updates == ["kubeai_mlops"]
        assert client.roles[0]["users"] == ["kubeai/alice"]

    async def test_noop_when_already_in_sync(self):
        user = _make_oidc_user()
        client = FakeCasdoorClient(
            roles=[
                {"name": "kubeai_mlops", "users": ["kubeai/alice"]},
                {"name": "kubeai_admin", "users": []},
            ]
        )

        await sync_role_to_casdoor(user, UserRole.MLOPS, client=client)

        assert client.updates == []

    async def test_missing_target_role_raises(self):
        user = _make_oidc_user()
        client = FakeCasdoorClient(roles=[{"name": "kubeai_engineer", "users": ["kubeai/alice"]}])

        with pytest.raises(ExternalServiceException, match="kubeai_admin"):
            await sync_role_to_casdoor(user, UserRole.ADMIN, client=client)

        assert client.updates == []
        assert client.roles[0]["users"] == ["kubeai/alice"]

    async def test_bare_id_external_id_resolved_to_owner_name(self):
        user = _make_oidc_user(external_id=UUID)
        client = FakeCasdoorClient(
            roles=[
                {"name": "kubeai_mlops", "users": ["chalco/kubeai_mlops"]},
                {"name": "kubeai_admin", "users": [UUID]},
            ],
            users={UUID: {"owner": "chalco", "name": "kubeai_mlops"}},
        )

        await sync_role_to_casdoor(user, UserRole.ADMIN, client=client)

        by_name = {r["name"]: r["users"] for r in client.roles}
        # 归一化后的 owner/name 命中 kubeai_mlops 旧成员并被移除, 加入 kubeai_admin
        assert by_name["kubeai_mlops"] == []
        assert by_name["kubeai_admin"] == [UUID, "chalco/kubeai_mlops"]

    async def test_unresolvable_external_id_raises(self):
        user = _make_oidc_user(external_id="unknown-ref")
        client = FakeCasdoorClient(roles=[{"name": "kubeai_admin", "users": []}])

        with pytest.raises(ExternalServiceException, match="unknown-ref"):
            await sync_role_to_casdoor(user, UserRole.ADMIN, client=client)

        assert client.updates == []
