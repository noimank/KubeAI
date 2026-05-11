"""Unit tests for PrometheusClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.integrations.prometheus.client import PrometheusClient


def _make_response(json_data: dict[str, Any], status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code, json=json_data, request=httpx.Request("GET", "http://localhost:9090/api/v1/query")
    )


@pytest.fixture
def client() -> PrometheusClient:
    return PrometheusClient(base_url="http://localhost:9090")


class TestPrometheusClient:
    async def test_instant_query_parses_response(self, client: PrometheusClient) -> None:
        prom_response = _make_response(
            {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {
                                "__name__": "DCGM_FI_DEV_GPU_UTIL",
                                "gpu": "0",
                                "namespace": "kubeai-tenant1",
                                "pod": "training-xxx-master-0",
                            },
                            "value": [1715401200.0, "87.5"],
                        }
                    ],
                },
            }
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = prom_response
        mock_client.is_closed = False

        with patch.object(client, "_get_client", return_value=mock_client):
            data = await client.instant_query('DCGM_FI_DEV_GPU_UTIL{namespace="kubeai-tenant1"}')

        assert data["resultType"] == "vector"
        assert len(data["result"]) == 1
        assert data["result"][0]["value"][1] == "87.5"

    async def test_range_query_parses_response(self, client: PrometheusClient) -> None:
        prom_response = _make_response(
            {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"gpu": "0", "pod": "training-xxx-master-0"},
                            "values": [
                                [1715400000.0, "85.2"],
                                [1715400015.0, "87.5"],
                            ],
                        }
                    ],
                },
            }
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = prom_response

        with patch.object(client, "_get_client", return_value=mock_client):
            data = await client.range_query(
                'DCGM_FI_DEV_GPU_UTIL{namespace="kubeai-tenant1"}',
                start="1715400000",
                end="1715401200",
                step="15s",
            )

        assert data["resultType"] == "matrix"
        assert len(data["result"][0]["values"]) == 2

    async def test_query_gpu_metrics_builds_correct_filter(self, client: PrometheusClient) -> None:
        prom_response = _make_response(
            {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "0"},
                            "value": [1715401200.0, "87.5"],
                        },
                        {
                            "metric": {"__name__": "DCGM_FI_DEV_FB_USED", "gpu": "0"},
                            "value": [1715401200.0, "8192"],
                        },
                    ],
                },
            }
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = prom_response

        with patch.object(client, "_get_client", return_value=mock_client):
            result = await client.query_gpu_metrics("kubeai-tenant1", "training-xxx-master-0")

        assert len(result) == 2
        # Verify the query parameter contains correct label filters
        call_args = mock_client.get.call_args
        query_param = call_args.kwargs.get("params", {}).get("query", "")
        assert 'namespace="kubeai-tenant1"' in query_param
        assert 'pod="training-xxx-master-0"' in query_param

    async def test_failed_query_raises_runtime_error(self, client: PrometheusClient) -> None:
        prom_response = _make_response(
            {
                "status": "error",
                "error": "bad query",
            }
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = prom_response

        with (
            patch.object(client, "_get_client", return_value=mock_client),
            pytest.raises(RuntimeError, match="Prometheus query failed"),
        ):
            await client.instant_query("invalid query")

    async def test_close_client(self) -> None:
        c = PrometheusClient(base_url="http://localhost:9090")
        c._client = httpx.AsyncClient()
        assert not c._client.is_closed
        await c.close()
        assert c._client.is_closed

    async def test_close_idempotent(self, client: PrometheusClient) -> None:
        await client.close()
        await client.close()  # should not raise
