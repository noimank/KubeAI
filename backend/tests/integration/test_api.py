import pytest

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ExternalServiceException,
    ForbiddenException,
    NotFoundException,
    QuotaExceededException,
    UnauthorizedException,
)


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_openapi_docs(client):
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_openapi_json(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert body["info"]["title"] == "KubeAI"
    assert "/api/health" in body["paths"]
