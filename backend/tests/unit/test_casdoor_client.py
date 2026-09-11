from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ExternalServiceException
from app.integrations.casdoor.client import CasdoorClient


@pytest.fixture
def casdoor():
    with patch("app.integrations.casdoor.client.settings") as mock_settings:
        mock_settings.OIDC_ISSUER = "http://casdoor.kubeai.local"
        mock_settings.OIDC_CLIENT_ID = "client-id"
        mock_settings.OIDC_CLIENT_SECRET = "client-secret"
        client = CasdoorClient()
    return client


def _ok_response(data):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "ok", "msg": "", "data": data}
    return resp


class TestGetKubeaiRoles:
    async def test_filters_by_prefix(self, casdoor):
        casdoor._httpx.request = AsyncMock(
            return_value=_ok_response(
                [
                    {"name": "kubeai_admin", "users": ["built-in/admin"]},
                    {"name": "org_role", "users": []},
                    {"name": "kubeai_engineer", "users": []},
                ]
            )
        )

        roles = await casdoor.get_kubeai_roles()
        assert [r["name"] for r in roles] == ["kubeai_admin", "kubeai_engineer"]

    async def test_raises_on_error_status(self, casdoor):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"status": "error", "msg": "unauthorized", "data": None}
        casdoor._httpx.request = AsyncMock(return_value=resp)

        with pytest.raises(ExternalServiceException, match="unauthorized"):
            await casdoor.get_kubeai_roles()

    async def test_raises_on_http_error(self, casdoor):
        casdoor._httpx.request = AsyncMock(return_value=MagicMock(status_code=401))

        with pytest.raises(ExternalServiceException, match="401"):
            await casdoor.get_kubeai_roles()


class TestUpdateRole:
    async def test_posts_full_role_object_with_id_param(self, casdoor):
        casdoor._httpx.request = AsyncMock(return_value=_ok_response(True))
        role = {"owner": "kubeai", "name": "kubeai_mlops", "users": ["kubeai/alice"]}

        await casdoor.update_role(role)

        casdoor._httpx.request.assert_awaited_once_with(
            "POST", "/api/update-role", params={"id": "kubeai/kubeai_mlops"}, json=role
        )

    async def test_non_json_response_raises(self, casdoor):
        resp = MagicMock(status_code=200)
        resp.text = "\n<!DOCTYPE html><html>beego application error</html>"
        resp.json.side_effect = ValueError("Expecting value")
        casdoor._httpx.request = AsyncMock(return_value=resp)

        with pytest.raises(ExternalServiceException, match="非 JSON"):
            await casdoor.get_kubeai_roles()
