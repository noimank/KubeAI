from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
async def test_oauth_providers_returns_empty_when_disabled(client: AsyncClient):
    with patch("app.api.endpoints.auth.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = False
        response = await client.get("/api/auth/oauth/providers")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []


@pytest.mark.asyncio(loop_scope="session")
async def test_oauth_providers_returns_list_when_enabled(client: AsyncClient):
    with patch("app.api.endpoints.auth.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = True
        mock_settings.OIDC_DISPLAY_NAME = "SSO 登录"
        response = await client.get("/api/auth/oauth/providers")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "oidc"
        assert body["data"][0]["display_name"] == "SSO 登录"


@pytest.mark.asyncio(loop_scope="session")
async def test_oauth_authorize_returns_404_for_unknown_provider(client: AsyncClient):
    with patch("app.api.endpoints.auth.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = True
        response = await client.get("/api/auth/oauth/unknown/authorize", follow_redirects=False)
        assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
async def test_oauth_authorize_disabled_returns_404(client: AsyncClient):
    with patch("app.api.endpoints.auth.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = False
        response = await client.get("/api/auth/oauth/oidc/authorize", follow_redirects=False)
        assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
async def test_oauth_callback_invalid_state_returns_401(client: AsyncClient):
    with patch("app.api.endpoints.auth.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = True
        response = await client.post(
            "/api/auth/oauth/oidc/callback",
            json={"code": "some-code", "state": "invalid-state"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_oauth_callback_disabled_returns_404(client: AsyncClient):
    with patch("app.api.endpoints.auth.settings") as mock_settings:
        mock_settings.OIDC_ENABLED = False
        response = await client.post(
            "/api/auth/oauth/oidc/callback",
            json={"code": "some-code", "state": "some-state"},
        )
        assert response.status_code == 404
