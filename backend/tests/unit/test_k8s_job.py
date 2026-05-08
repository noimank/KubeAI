from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

from app.integrations.k8s import job as k8s_job


@pytest.fixture
def mock_k8s_clients():
    with patch("app.integrations.k8s.job.get_k8s_clients") as mock:
        core_v1 = MagicMock()
        batch_v1 = MagicMock()
        mock.return_value = {"core_v1": core_v1, "batch_v1": batch_v1}
        yield {"core_v1": core_v1, "batch_v1": batch_v1}


class TestCreateConfigMap:
    def test_create_new(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].create_namespaced_config_map.return_value = MagicMock()
        result = k8s_job.create_configmap("ns", "test-cm", {"key": "value"})
        assert result is not None
        mock_k8s_clients["core_v1"].create_namespaced_config_map.assert_called_once()

    def test_create_already_exists(self, mock_k8s_clients):
        error = ApiException(status=409)
        mock_k8s_clients["core_v1"].create_namespaced_config_map.side_effect = error
        mock_k8s_clients["core_v1"].replace_namespaced_config_map.return_value = MagicMock()
        k8s_job.create_configmap("ns", "test-cm", {"key": "value"})
        mock_k8s_clients["core_v1"].replace_namespaced_config_map.assert_called_once()


class TestDeleteConfigMap:
    def test_delete_existing(self, mock_k8s_clients):
        k8s_job.delete_configmap("ns", "test-cm")
        mock_k8s_clients["core_v1"].delete_namespaced_config_map.assert_called_once()

    def test_delete_not_found(self, mock_k8s_clients):
        error = ApiException(status=404)
        mock_k8s_clients["core_v1"].delete_namespaced_config_map.side_effect = error
        k8s_job.delete_configmap("ns", "missing-cm")


class TestCreateBuildJob:
    def test_creates_job_object(self):
        job = k8s_job.create_build_job(
            namespace="ns",
            job_name="test-job",
            dockerfile_configmap="test-cm",
            destination="harbor.local/proj/img:v1",
            harbor_url="http://harbor.local",
        )
        assert job.metadata.name == "test-job"
        assert job.metadata.namespace == "ns"
        assert job.spec.backoff_limit == 0
        assert job.spec.ttl_seconds_after_finished == 3600


class TestSubmitJob:
    def test_submit_success(self, mock_k8s_clients):
        mock_k8s_clients["batch_v1"].create_namespaced_job.return_value = MagicMock()
        job_obj = MagicMock()
        job_obj.metadata.name = "test-job"
        k8s_job.submit_job("ns", job_obj)
        mock_k8s_clients["batch_v1"].create_namespaced_job.assert_called_once()


class TestGetJobStatus:
    def test_succeeded(self, mock_k8s_clients):
        mock_job = MagicMock()
        mock_job.status.succeeded = 1
        mock_job.status.failed = None
        mock_job.status.active = None
        mock_k8s_clients["batch_v1"].read_namespaced_job.return_value = mock_job
        result = k8s_job.get_job_status("ns", "test-job")
        assert result["status"] == "succeeded"

    def test_failed(self, mock_k8s_clients):
        mock_job = MagicMock()
        mock_job.status.succeeded = None
        mock_job.status.failed = 1
        mock_job.status.active = None
        mock_k8s_clients["batch_v1"].read_namespaced_job.return_value = mock_job
        result = k8s_job.get_job_status("ns", "test-job")
        assert result["status"] == "failed"

    def test_running(self, mock_k8s_clients):
        mock_job = MagicMock()
        mock_job.status.succeeded = None
        mock_job.status.failed = None
        mock_job.status.active = 1
        mock_k8s_clients["batch_v1"].read_namespaced_job.return_value = mock_job
        result = k8s_job.get_job_status("ns", "test-job")
        assert result["status"] == "running"

    def test_not_found(self, mock_k8s_clients):
        error = ApiException(status=404)
        mock_k8s_clients["batch_v1"].read_namespaced_job.side_effect = error
        result = k8s_job.get_job_status("ns", "missing-job")
        assert result["exists"] is False

    def test_pending(self, mock_k8s_clients):
        mock_job = MagicMock()
        mock_job.status.succeeded = None
        mock_job.status.failed = None
        mock_job.status.active = None
        mock_k8s_clients["batch_v1"].read_namespaced_job.return_value = mock_job
        result = k8s_job.get_job_status("ns", "test-job")
        assert result["status"] == "pending"


class TestGetJobLogs:
    def test_get_logs_success(self, mock_k8s_clients):
        mock_pod = MagicMock()
        mock_pod.metadata.name = "test-job-pod"
        mock_k8s_clients["core_v1"].list_namespaced_pod.return_value = MagicMock(items=[mock_pod])
        mock_k8s_clients["core_v1"].read_namespaced_pod_log.return_value = "build log output"
        result = k8s_job.get_job_logs("ns", "test-job")
        assert result == "build log output"

    def test_get_logs_no_pods(self, mock_k8s_clients):
        mock_k8s_clients["core_v1"].list_namespaced_pod.return_value = MagicMock(items=[])
        result = k8s_job.get_job_logs("ns", "test-job")
        assert result == ""


class TestDeleteJob:
    def test_delete_success(self, mock_k8s_clients):
        k8s_job.delete_job("ns", "test-job")
        mock_k8s_clients["batch_v1"].delete_namespaced_job.assert_called_once()

    def test_delete_not_found(self, mock_k8s_clients):
        error = ApiException(status=404)
        mock_k8s_clients["batch_v1"].delete_namespaced_job.side_effect = error
        k8s_job.delete_job("ns", "missing-job")


class TestNaming:
    def test_make_job_name(self):
        name = k8s_job.make_job_name("my-image")
        assert name == "image-build-my-image"

    def test_make_configmap_name(self):
        name = k8s_job.make_configmap_name("my-image")
        assert name == "dockerfile-my-image"

    def test_make_job_name_sanitized(self):
        name = k8s_job.make_job_name("My_Image:v1.0")
        assert name == "image-build-my-image-v1-0"
