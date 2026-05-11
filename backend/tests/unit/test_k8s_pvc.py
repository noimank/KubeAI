from unittest.mock import AsyncMock, MagicMock, patch

from kubernetes_asyncio.client.rest import ApiException

from app.integrations.k8s.pvc import (
    create_pvc,
    delete_pvc,
    get_pvc,
    make_dataset_pvc_name,
    pvc_exists,
)


def _make_mock_pvc(name: str = "test-pvc", phase: str = "Bound") -> MagicMock:
    pvc = MagicMock()
    pvc.metadata.name = name
    pvc.status.phase = phase
    return pvc


class TestMakeDatasetPvcName:
    def test_format(self):
        name = make_dataset_pvc_name("my-dataset", 3)
        assert name == "dataset-my-dataset-v3"

    def test_sanitized_name(self):
        name = make_dataset_pvc_name("My Dataset!", 1)
        assert name == "dataset-my-dataset-v1"

    def test_version_number(self):
        name = make_dataset_pvc_name("test-data", 42)
        assert name == "dataset-test-data-v42"


class TestCreatePvc:
    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_create_success(self, mock_get_clients):
        mock_api = MagicMock()
        mock_pvc = _make_mock_pvc()
        mock_api.create_namespaced_persistent_volume_claim = AsyncMock(return_value=mock_pvc)
        mock_get_clients.return_value = {"core_v1": mock_api}

        result = await create_pvc("kubeai-test", "test-pvc", "1Gi")
        assert result == mock_pvc
        mock_api.create_namespaced_persistent_volume_claim.assert_called_once()
        call_kwargs = mock_api.create_namespaced_persistent_volume_claim.call_args
        body = call_kwargs.kwargs["body"] if "body" in call_kwargs.kwargs else call_kwargs[1][0]
        assert body.metadata.name == "test-pvc"
        assert body.metadata.labels["app.kubernetes.io/managed-by"] == "kubeai"

    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_create_already_exists_409(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.create_namespaced_persistent_volume_claim = AsyncMock(side_effect=ApiException(status=409))
        existing_pvc = _make_mock_pvc("existing")
        mock_api.read_namespaced_persistent_volume_claim = AsyncMock(return_value=existing_pvc)
        mock_get_clients.return_value = {"core_v1": mock_api}

        result = await create_pvc("kubeai-test", "existing-pvc", "2Gi")
        assert result == existing_pvc
        mock_api.read_namespaced_persistent_volume_claim.assert_called_once_with(
            name="existing-pvc", namespace="kubeai-test"
        )

    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_create_other_error_raises(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.create_namespaced_persistent_volume_claim = AsyncMock(side_effect=ApiException(status=500))
        mock_get_clients.return_value = {"core_v1": mock_api}

        import pytest

        with pytest.raises(ApiException):
            await create_pvc("kubeai-test", "test-pvc", "1Gi")

    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_create_with_storage_class(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.create_namespaced_persistent_volume_claim = AsyncMock(return_value=_make_mock_pvc())
        mock_get_clients.return_value = {"core_v1": mock_api}

        await create_pvc("kubeai-test", "test-pvc", "1Gi", storage_class="nfs")
        call_kwargs = mock_api.create_namespaced_persistent_volume_claim.call_args
        body = call_kwargs.kwargs["body"] if "body" in call_kwargs.kwargs else call_kwargs[1][0]
        assert body.spec.storage_class_name == "nfs"

    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_create_no_storage_class(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.create_namespaced_persistent_volume_claim = AsyncMock(return_value=_make_mock_pvc())
        mock_get_clients.return_value = {"core_v1": mock_api}

        await create_pvc("kubeai-test", "test-pvc", "1Gi")
        call_kwargs = mock_api.create_namespaced_persistent_volume_claim.call_args
        body = call_kwargs.kwargs["body"] if "body" in call_kwargs.kwargs else call_kwargs[1][0]
        assert body.spec.storage_class_name is None


class TestPvcExists:
    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_exists(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.read_namespaced_persistent_volume_claim = AsyncMock(return_value=_make_mock_pvc())
        mock_get_clients.return_value = {"core_v1": mock_api}

        assert await pvc_exists("kubeai-test", "test-pvc") is True

    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_not_found(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.read_namespaced_persistent_volume_claim = AsyncMock(side_effect=ApiException(status=404))
        mock_get_clients.return_value = {"core_v1": mock_api}

        assert await pvc_exists("kubeai-test", "test-pvc") is False

    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_other_error_raises(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.read_namespaced_persistent_volume_claim = AsyncMock(side_effect=ApiException(status=403))
        mock_get_clients.return_value = {"core_v1": mock_api}

        import pytest

        with pytest.raises(ApiException):
            await pvc_exists("kubeai-test", "test-pvc")


class TestGetPvc:
    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_get_success(self, mock_get_clients):
        mock_api = MagicMock()
        mock_pvc = _make_mock_pvc("test-pvc", "Bound")
        mock_api.read_namespaced_persistent_volume_claim = AsyncMock(return_value=mock_pvc)
        mock_get_clients.return_value = {"core_v1": mock_api}

        result = await get_pvc("kubeai-test", "test-pvc")
        assert result == mock_pvc


class TestDeletePvc:
    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_delete_success(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.delete_namespaced_persistent_volume_claim = AsyncMock()
        mock_get_clients.return_value = {"core_v1": mock_api}

        await delete_pvc("kubeai-test", "test-pvc")
        mock_api.delete_namespaced_persistent_volume_claim.assert_called_once_with(
            name="test-pvc", namespace="kubeai-test"
        )

    @patch("app.integrations.k8s.pvc.get_k8s_clients", new_callable=AsyncMock)
    async def test_delete_not_found(self, mock_get_clients):
        mock_api = MagicMock()
        mock_api.delete_namespaced_persistent_volume_claim = AsyncMock(side_effect=ApiException(status=404))
        mock_get_clients.return_value = {"core_v1": mock_api}

        await delete_pvc("kubeai-test", "test-pvc")
