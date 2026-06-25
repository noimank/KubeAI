from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError
from kubernetes_asyncio.client.rest import ApiException  # type: ignore[import-untyped]

from app.integrations.k8s import pod as k8s_pod


@pytest.fixture
def mock_k8s_clients():
    with patch("app.integrations.k8s.pod.get_k8s_clients", new_callable=AsyncMock) as mock:
        core_v1 = MagicMock()
        mock.return_value = {"core_v1": core_v1}
        yield {"core_v1": core_v1}


class TestParsePodRole:
    def test_master_pod(self):
        assert k8s_pod._parse_pod_role("training-job-master-0") == "master"

    def test_worker_pod(self):
        assert k8s_pod._parse_pod_role("training-job-worker-0") == "worker-0"

    def test_worker_pod_higher_index(self):
        assert k8s_pod._parse_pod_role("training-job-worker-3") == "worker-3"

    def test_no_match_defaults_to_master(self):
        assert k8s_pod._parse_pod_role("some-random-pod") == "master"


class _AsyncIter:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration as err:
            raise StopAsyncIteration from err


class TestStreamPodLogs:
    async def test_stream_reads_lines(self, mock_k8s_clients):
        mock_content = _AsyncIter([b"line1\n", b"line2\n"])

        mock_resp = MagicMock()
        mock_resp.content = mock_content
        mock_resp.close = MagicMock()

        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(return_value=mock_resp)

        lines = []
        async for line in k8s_pod.stream_pod_logs("ns", "pod-1", tail_lines=100):
            lines.append(line)

        assert lines == ["line1", "line2"]
        mock_resp.close.assert_called_once()

    async def test_stream_passes_kwargs(self, mock_k8s_clients):
        mock_resp = MagicMock()
        mock_resp.content = _AsyncIter([])
        mock_resp.close = MagicMock()

        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(return_value=mock_resp)

        async for _ in k8s_pod.stream_pod_logs("ns", "pod-1", container="main", tail_lines=50):
            pass

        call_kwargs = mock_k8s_clients["core_v1"].read_namespaced_pod_log.call_args[1]
        assert call_kwargs["container"] == "main"
        assert call_kwargs["tail_lines"] == 50
        assert call_kwargs["follow"] is True
        assert call_kwargs["_preload_content"] is False

    async def test_stream_no_container_excluded(self, mock_k8s_clients):
        mock_resp = MagicMock()
        mock_resp.content = _AsyncIter([])
        mock_resp.close = MagicMock()

        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(return_value=mock_resp)

        async for _ in k8s_pod.stream_pod_logs("ns", "pod-1"):
            pass

        call_kwargs = mock_k8s_clients["core_v1"].read_namespaced_pod_log.call_args[1]
        assert "container" not in call_kwargs

    async def test_stream_pod_not_ready_ends_gracefully(self, mock_k8s_clients):
        # Container still starting (Pending / ContainerCreating) → K8s returns 400.
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(side_effect=ApiException(status=400))

        lines = [line async for line in k8s_pod.stream_pod_logs("ns", "pod-1")]

        assert lines == []

    async def test_stream_pod_not_found_ends_gracefully(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(side_effect=ApiException(status=404))

        lines = [line async for line in k8s_pod.stream_pod_logs("ns", "missing")]

        assert lines == []

    async def test_stream_server_error_raises(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(side_effect=ApiException(status=500))

        with pytest.raises(ApiException):
            async for _ in k8s_pod.stream_pod_logs("ns", "pod-1"):
                pass

    async def test_stream_mid_stream_error_ends_cleanly(self, mock_k8s_clients):
        class _ErrorContent:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise ClientError("connection reset")

        mock_resp = MagicMock()
        mock_resp.content = _ErrorContent()
        mock_resp.close = MagicMock()
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(return_value=mock_resp)

        lines = [line async for line in k8s_pod.stream_pod_logs("ns", "pod-1")]

        assert lines == []
        mock_resp.close.assert_called_once()


class TestListVcjobPods:
    async def test_list_pods(self, mock_k8s_clients):
        mock_pod1 = MagicMock()
        mock_pod1.metadata.name = "training-job-master-0"
        mock_pod1.status.phase = "Running"

        mock_pod2 = MagicMock()
        mock_pod2.metadata.name = "training-job-worker-0"
        mock_pod2.status.phase = "Running"

        mock_k8s_clients["core_v1"].list_namespaced_pod = AsyncMock(
            return_value=MagicMock(items=[mock_pod1, mock_pod2])
        )

        result = await k8s_pod.list_vcjob_pods("ns", "training-job")

        assert len(result) == 2
        assert result[0] == {"pod_name": "training-job-master-0", "role": "master", "status": "running"}
        assert result[1] == {"pod_name": "training-job-worker-0", "role": "worker-0", "status": "running"}

    async def test_list_empty(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].list_namespaced_pod = AsyncMock(return_value=MagicMock(items=[]))
        result = await k8s_pod.list_vcjob_pods("ns", "training-job")
        assert result == []

    async def test_skips_pods_without_metadata(self, mock_k8s_clients):
        mock_pod = MagicMock()
        mock_pod.metadata = None
        mock_pod.status = MagicMock()

        mock_k8s_clients["core_v1"].list_namespaced_pod = AsyncMock(return_value=MagicMock(items=[mock_pod]))

        result = await k8s_pod.list_vcjob_pods("ns", "training-job")
        assert result == []

    async def test_pods_sorted_master_first_then_workers_by_index(self, mock_k8s_clients):
        # K8s returns pods in arbitrary order; the default pod must be the chief
        # (master) deterministically, not whatever the API happened to list first.
        def make_pod(name: str):
            pod = MagicMock()
            pod.metadata.name = name
            pod.status.phase = "Running"
            return pod

        pods = [
            make_pod("job-worker-2"),
            make_pod("job-master-0"),
            make_pod("job-worker-0"),
            make_pod("job-worker-1"),
        ]
        mock_k8s_clients["core_v1"].list_namespaced_pod = AsyncMock(return_value=MagicMock(items=pods))

        result = await k8s_pod.list_vcjob_pods("ns", "job")

        assert [p["pod_name"] for p in result] == [
            "job-master-0",
            "job-worker-0",
            "job-worker-1",
            "job-worker-2",
        ]


class TestGetPodLog:
    async def test_get_log_success(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(return_value="log line 1\nlog line 2")
        result = await k8s_pod.get_pod_log("ns", "pod-1")
        assert result == "log line 1\nlog line 2"

    async def test_get_log_not_found(self, mock_k8s_clients):
        error = ApiException(status=404)
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(side_effect=error)
        result = await k8s_pod.get_pod_log("ns", "missing-pod")
        assert result == ""

    async def test_get_log_bad_request(self, mock_k8s_clients):
        error = ApiException(status=400)
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(side_effect=error)
        result = await k8s_pod.get_pod_log("ns", "pod-1")
        assert result == ""

    async def test_get_log_server_error_raises(self, mock_k8s_clients):
        error = ApiException(status=500)
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(side_effect=error)
        with pytest.raises(ApiException):
            await k8s_pod.get_pod_log("ns", "pod-1")

    async def test_get_log_with_container(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(return_value="log output")
        await k8s_pod.get_pod_log("ns", "pod-1", container="main", tail_lines=500)
        call_kwargs = mock_k8s_clients["core_v1"].read_namespaced_pod_log.call_args[1]
        assert call_kwargs["container"] == "main"
        assert call_kwargs["tail_lines"] == 500

    async def test_get_log_without_container(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(return_value="log output")
        await k8s_pod.get_pod_log("ns", "pod-1")
        call_kwargs = mock_k8s_clients["core_v1"].read_namespaced_pod_log.call_args[1]
        assert "container" not in call_kwargs

    async def test_get_log_requests_timestamps(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].read_namespaced_pod_log = AsyncMock(return_value="2024-01-01T00:00:00Z line")
        await k8s_pod.get_pod_log("ns", "pod-1")
        call_kwargs = mock_k8s_clients["core_v1"].read_namespaced_pod_log.call_args[1]
        assert call_kwargs["timestamps"] is True


class TestGetPodFailureInfo:
    def _make_terminated(self, exit_code=0, reason="", message="", signal=None):
        t = MagicMock()
        t.exit_code = exit_code
        t.reason = reason
        t.message = message
        t.signal = signal
        t.finished_at = None
        return t

    def _make_container_status(self, terminated=None, waiting=None):
        state = MagicMock()
        state.terminated = terminated
        state.waiting = waiting
        cs = MagicMock()
        cs.state = state
        return cs

    async def test_terminated_pod_returns_info(self, mock_k8s_clients):
        terminated = self._make_terminated(exit_code=137, reason="OOMKilled", message="Out of memory")
        cs = self._make_container_status(terminated=terminated)

        pod = MagicMock()
        pod.status.container_statuses = [cs]
        mock_k8s_clients["core_v1"].read_namespaced_pod = AsyncMock(return_value=pod)

        result = await k8s_pod.get_pod_failure_info("ns", "pod-1")
        assert result is not None
        assert result["exit_code"] == 137
        assert result["reason"] == "OOMKilled"

    async def test_image_pull_backoff(self, mock_k8s_clients):
        waiting = MagicMock()
        waiting.reason = "ImagePullBackOff"
        waiting.message = "Back-off pulling image"
        cs = self._make_container_status(waiting=waiting)

        pod = MagicMock()
        pod.status.container_statuses = [cs]
        mock_k8s_clients["core_v1"].read_namespaced_pod = AsyncMock(return_value=pod)

        result = await k8s_pod.get_pod_failure_info("ns", "pod-1")
        assert result is not None
        assert result["reason"] == "ImagePullBackOff"

    async def test_no_container_statuses(self, mock_k8s_clients):
        pod = MagicMock()
        pod.status.container_statuses = None
        mock_k8s_clients["core_v1"].read_namespaced_pod = AsyncMock(return_value=pod)

        result = await k8s_pod.get_pod_failure_info("ns", "pod-1")
        assert result is None

    async def test_pod_not_found(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].read_namespaced_pod = AsyncMock(side_effect=ApiException(status=404))

        result = await k8s_pod.get_pod_failure_info("ns", "missing-pod")
        assert result is None

    async def test_running_pod_no_failure(self, mock_k8s_clients):
        cs = self._make_container_status(terminated=None, waiting=None)

        pod = MagicMock()
        pod.status.container_statuses = [cs]
        mock_k8s_clients["core_v1"].read_namespaced_pod = AsyncMock(return_value=pod)

        result = await k8s_pod.get_pod_failure_info("ns", "pod-1")
        assert result is None
