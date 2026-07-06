"""Unit tests for app.core.gpu_metrics — shared GPU metric parsing utilities."""

from __future__ import annotations

from datetime import timedelta

from app.core.gpu_metrics import (
    MetricsResponse,
    degraded_response,
    metrics_success,
    parse_duration,
    parse_gpu_history,
    parse_gpu_metrics,
)


class TestParseGpuMetrics:
    def test_parses_single_gpu(self) -> None:
        raw = [
            {
                "metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "0"},
                "value": [1715401200.0, "87.5"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_FB_USED", "gpu": "0"},
                "value": [1715401200.0, "8192"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_FB_FREE", "gpu": "0"},
                "value": [1715401200.0, "8192"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_GPU_TEMP", "gpu": "0"},
                "value": [1715401200.0, "72"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_POWER_USAGE", "gpu": "0"},
                "value": [1715401200.0, "250"],
            },
        ]

        result = parse_gpu_metrics(raw)
        assert len(result) == 1
        gpu = result[0]
        assert gpu["gpu_index"] == 0
        assert gpu["utilization_percent"] == 87.5
        assert gpu["memory_used_mib"] == 8192
        assert gpu["memory_total_mib"] == 16384
        assert gpu["temperature_c"] == 72
        assert gpu["power_w"] == 250

    def test_parses_multiple_gpus(self) -> None:
        raw = [
            {"metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "0"}, "value": [0, "80"]},
            {"metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "1"}, "value": [0, "60"]},
        ]

        result = parse_gpu_metrics(raw)
        assert len(result) == 2
        assert result[0]["gpu_index"] == 0
        assert result[1]["gpu_index"] == 1

    def test_empty_results(self) -> None:
        assert parse_gpu_metrics([]) == []

    def test_missing_metrics_default_to_zero(self) -> None:
        raw = [
            {"metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "0"}, "value": [0, "50"]},
        ]

        result = parse_gpu_metrics(raw)
        assert len(result) == 1
        gpu = result[0]
        assert gpu["utilization_percent"] == 50
        assert gpu["memory_used_mib"] == 0
        assert gpu["temperature_c"] == 0


class TestParseGpuHistory:
    def test_parses_time_series(self) -> None:
        raw = [
            {
                "metric": {"gpu": "0", "pod": "pod-1"},
                "values": [[1715400000.0, "85.2"], [1715400015.0, "87.5"]],
            }
        ]

        result = parse_gpu_history(raw)
        assert len(result) == 2
        assert result[0]["label"] == "GPU 0"
        assert result[0]["value"] == 85.2
        assert result[1]["value"] == 87.5

    def test_empty_results(self) -> None:
        assert parse_gpu_history([]) == []

    def test_multiple_series(self) -> None:
        raw = [
            {"metric": {"gpu": "0"}, "values": [[1715400000.0, "80"]]},
            {"metric": {"gpu": "1"}, "values": [[1715400000.0, "60"]]},
        ]

        result = parse_gpu_history(raw)
        assert len(result) == 2
        assert result[0]["label"] == "GPU 0"
        assert result[1]["label"] == "GPU 1"


class TestParseDuration:
    def test_minutes(self) -> None:
        assert parse_duration("20m") == timedelta(minutes=20)

    def test_hours(self) -> None:
        assert parse_duration("1h") == timedelta(hours=1)

    def test_seconds(self) -> None:
        assert parse_duration("30s") == timedelta(seconds=30)

    def test_invalid_defaults_to_20m(self) -> None:
        assert parse_duration("invalid") == timedelta(minutes=20)


class TestResponseHelpers:
    def test_degraded_response(self) -> None:
        resp = degraded_response("http://example.com")
        assert resp["gpu_metrics"] == []
        assert resp["gpu_utilization_history"] == []
        assert resp["metrics_url"] == "http://example.com"
        assert resp["prometheus_available"] is False
        assert isinstance(resp["timestamp"], str)

    def test_degraded_response_no_url(self) -> None:
        resp = degraded_response()
        assert resp["metrics_url"] is None

    def test_metrics_success(self) -> None:
        gpu = [{"gpu_index": 0, "utilization_percent": 80}]
        hist = [{"timestamp": "2026-01-01T00:00:00Z", "value": 85, "label": "GPU 0"}]
        resp = metrics_success(gpu, hist, "http://x")
        assert resp["gpu_metrics"] is gpu
        assert resp["gpu_utilization_history"] is hist
        assert resp["metrics_url"] == "http://x"
        assert resp["prometheus_available"] is True


class TestMetricsResponseModel:
    def test_constructs_from_dict(self) -> None:
        data = {
            "gpu_metrics": [],
            "gpu_utilization_history": [],
            "metrics_url": None,
            "prometheus_available": True,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        model = MetricsResponse(**data)
        assert model.gpu_metrics == []
        assert model.prometheus_available is True
