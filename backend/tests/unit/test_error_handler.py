import json
from unittest.mock import MagicMock

from fastapi import Request

from app.core.exceptions import NotFoundException
from app.middleware.error_handler import app_exception_handler, unhandled_exception_handler


def _make_request(request_id: str | None) -> Request:
    request = MagicMock(spec=Request)
    request.method = "DELETE"
    request.url.path = "/api/datasets/123"
    request.state.request_id = request_id
    return request


class TestUnhandledExceptionHandler:
    async def test_response_exposes_exception_detail_and_request_id(self):
        request = _make_request(request_id="abc123")
        exc = RuntimeError("boom")

        response = await unhandled_exception_handler(request, exc)

        assert response.status_code == 500
        payload = json.loads(response.body)
        assert payload["success"] is False
        assert payload["data"] is None
        assert "RuntimeError" in payload["message"]
        assert "boom" in payload["message"]
        assert "abc123" in payload["message"]
        assert response.headers["X-Request-ID"] == "abc123"

    async def test_response_without_request_id(self):
        request = _make_request(request_id=None)
        exc = ValueError("bad value")

        response = await unhandled_exception_handler(request, exc)

        assert response.status_code == 500
        payload = json.loads(response.body)
        assert "ValueError" in payload["message"]
        assert "bad value" in payload["message"]
        assert "request_id" not in payload["message"]

    async def test_exception_without_message_omits_detail_suffix(self):
        request = _make_request(request_id="rid-1")
        exc = RuntimeError()  # str(exc) == ""

        response = await unhandled_exception_handler(request, exc)

        payload = json.loads(response.body)
        assert payload["message"] == "服务内部错误: RuntimeError (request_id: rid-1)"


class TestAppExceptionHandler:
    async def test_preserves_business_exception_message(self):
        request = _make_request(request_id="rid-2")
        exc = NotFoundException("数据集不存在")

        response = await app_exception_handler(request, exc)

        assert response.status_code == 404
        payload = json.loads(response.body)
        assert payload["success"] is False
        assert payload["message"] == "数据集不存在"
