"""Unit tests for TrainingJobService metric parsing."""

from __future__ import annotations

from app.services.training_job_service import TrainingJobService


class TestParseGpuMetrics:
    def test_parses_single_gpu(self) -> None:
        raw = [
            {
                "metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "0", "namespace": "ns", "pod": "pod-1"},
                "value": [1715401200.0, "87.5"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_FB_USED", "gpu": "0", "namespace": "ns", "pod": "pod-1"},
                "value": [1715401200.0, "8192"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_FB_FREE", "gpu": "0", "namespace": "ns", "pod": "pod-1"},
                "value": [1715401200.0, "8192"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_GPU_TEMP", "gpu": "0", "namespace": "ns", "pod": "pod-1"},
                "value": [1715401200.0, "72"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_POWER_USAGE", "gpu": "0", "namespace": "ns", "pod": "pod-1"},
                "value": [1715401200.0, "250"],
            },
        ]

        result = TrainingJobService._parse_gpu_metrics(raw)
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
            {
                "metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "0"},
                "value": [0, "80"],
            },
            {
                "metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "1"},
                "value": [0, "60"],
            },
        ]

        result = TrainingJobService._parse_gpu_metrics(raw)
        assert len(result) == 2
        assert result[0]["gpu_index"] == 0
        assert result[1]["gpu_index"] == 1

    def test_empty_results(self) -> None:
        result = TrainingJobService._parse_gpu_metrics([])
        assert result == []

    def test_missing_metrics_default_to_zero(self) -> None:
        raw = [
            {
                "metric": {"__name__": "DCGM_FI_DEV_GPU_UTIL", "gpu": "0"},
                "value": [0, "50"],
            },
        ]

        result = TrainingJobService._parse_gpu_metrics(raw)
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
                "values": [
                    [1715400000.0, "85.2"],
                    [1715400015.0, "87.5"],
                ],
            }
        ]

        result = TrainingJobService._parse_gpu_history(raw)
        assert len(result) == 2
        assert result[0]["label"] == "GPU 0"
        assert result[0]["value"] == 85.2
        assert result[1]["value"] == 87.5

    def test_empty_results(self) -> None:
        result = TrainingJobService._parse_gpu_history([])
        assert result == []

    def test_multiple_series(self) -> None:
        raw = [
            {
                "metric": {"gpu": "0"},
                "values": [[1715400000.0, "80"]],
            },
            {
                "metric": {"gpu": "1"},
                "values": [[1715400000.0, "60"]],
            },
        ]

        result = TrainingJobService._parse_gpu_history(raw)
        assert len(result) == 2
        assert result[0]["label"] == "GPU 0"
        assert result[1]["label"] == "GPU 1"


class TestParseDuration:
    def test_minutes(self) -> None:
        from datetime import timedelta

        result = TrainingJobService._parse_duration("20m")
        assert result == timedelta(minutes=20)

    def test_hours(self) -> None:
        from datetime import timedelta

        result = TrainingJobService._parse_duration("1h")
        assert result == timedelta(hours=1)

    def test_seconds(self) -> None:
        from datetime import timedelta

        result = TrainingJobService._parse_duration("30s")
        assert result == timedelta(seconds=30)

    def test_invalid_defaults_to_20m(self) -> None:
        from datetime import timedelta

        result = TrainingJobService._parse_duration("invalid")
        assert result == timedelta(minutes=20)
