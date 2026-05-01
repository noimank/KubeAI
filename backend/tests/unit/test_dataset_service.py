import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import NotFoundException
from app.models.dataset import Dataset, DatasetVersion
from app.services.dataset_service import DatasetService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


_NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)


def _make_dataset(name="test-dataset", tenant_id=None):
    ds = Dataset(
        name=name,
        description="test description",
        tenant_id=tenant_id or uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    ds.id = uuid.uuid4()
    ds.created_at = _NOW
    ds.updated_at = _NOW
    ds.versions = []
    return ds


def _make_version(dataset_id=None, version_number=1):
    v = DatasetVersion(
        dataset_id=dataset_id or uuid.uuid4(),
        version_number=version_number,
        storage_path=f"datasets/{dataset_id}/v{version_number}/",
        file_count=0,
        total_size_bytes=0,
        created_by=uuid.uuid4(),
    )
    v.id = uuid.uuid4()
    v.created_at = _NOW
    v.updated_at = _NOW
    return v


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_minio():
    m = MagicMock()
    m.ensure_bucket = MagicMock()
    m.upload_stream = MagicMock()
    m.list_objects = MagicMock(return_value=[])
    m.delete_objects = MagicMock()
    m.presigned_get_url = MagicMock(return_value="https://minio.example.com/presigned-url")
    return m


@pytest.fixture
def service(mock_db, mock_minio):
    return DatasetService(mock_db, mock_minio)


class TestCreateDataset:
    async def test_create_dataset_success(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result = await service.create_dataset(
            tenant_id=tenant_id,
            user_id=user_id,
            name="my-dataset",
            description="A test dataset",
        )

        assert result.name == "my-dataset"
        assert result.description == "A test dataset"
        assert result.tenant_id == tenant_id
        assert result.created_by == user_id
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_create_dataset_with_audit(self, service, mock_db):
        with patch("app.services.dataset_service.AuditService") as mock_audit_cls:
            mock_audit = AsyncMock()
            mock_audit_cls.return_value = mock_audit

            await service.create_dataset(
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                name="ds",
                audit_context={"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"},
            )

            mock_audit.log_action.assert_called_once()


class TestUploadFilesToVersion:
    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_upload_files(self, mock_to_thread, service, mock_db, mock_minio):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id)
        dataset.versions = [version]

        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(version)]

        file1 = AsyncMock()
        file1.filename = "test.csv"
        file1.content_type = "text/csv"
        file1.read.return_value = b"hello world"

        result = await service.upload_files_to_version(
            tenant_id=dataset.tenant_id,
            dataset_id=dataset.id,
            version_id=version.id,
            files=[file1],
        )

        assert len(result) == 1
        assert result[0]["file_name"] == "test.csv"
        assert result[0]["size_bytes"] == 11

    async def test_upload_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.upload_files_to_version(
                tenant_id=uuid.uuid4(),
                dataset_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
                files=[],
            )


class TestCreateVersion:
    async def test_create_first_version(self, service, mock_db):
        dataset = _make_dataset()
        max_result = MagicMock()
        max_result.scalar.return_value = None

        mock_db.execute.side_effect = [_sync_result(dataset), max_result]

        result = await service.create_version(
            tenant_id=dataset.tenant_id,
            dataset_id=dataset.id,
            user_id=uuid.uuid4(),
        )

        assert result.version_number == 1
        assert result.file_count == 0
        assert result.total_size_bytes == 0

    async def test_create_next_version(self, service, mock_db):
        dataset = _make_dataset()
        max_result = MagicMock()
        max_result.scalar.return_value = 3

        mock_db.execute.side_effect = [_sync_result(dataset), max_result]

        result = await service.create_version(
            tenant_id=dataset.tenant_id,
            dataset_id=dataset.id,
            user_id=uuid.uuid4(),
            description="v4",
        )

        assert result.version_number == 4
        assert result.description == "v4"


class TestGetDataset:
    async def test_get_dataset_found(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.return_value = _sync_result(dataset)

        result = await service.get_dataset(dataset.id, dataset.tenant_id)
        assert result.name == "test-dataset"

    async def test_get_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.get_dataset(uuid.uuid4(), uuid.uuid4())


class TestListDatasets:
    async def test_list_empty(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        items, total = await service.list_datasets(tenant_id=uuid.uuid4())
        assert items == []
        assert total == 0

    async def test_list_with_keyword(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        await service.list_datasets(tenant_id=uuid.uuid4(), keyword="test")
        assert mock_db.execute.call_count == 2

    async def test_list_with_start_date(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        await service.list_datasets(tenant_id=uuid.uuid4(), start_date=date(2026, 1, 1))
        assert mock_db.execute.call_count == 2

    async def test_list_with_end_date(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        await service.list_datasets(tenant_id=uuid.uuid4(), end_date=date(2026, 4, 30))
        assert mock_db.execute.call_count == 2

    async def test_list_with_date_range(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        await service.list_datasets(
            tenant_id=uuid.uuid4(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 30),
        )
        assert mock_db.execute.call_count == 2


class TestDatasetAggregation:
    def test_build_dataset_response_aggregation(self):
        from app.api.endpoints.datasets import _build_dataset_response

        ds = _make_dataset()
        v1 = _make_version(dataset_id=ds.id, version_number=1)
        v1.file_count = 5
        v1.total_size_bytes = 1024
        v2 = _make_version(dataset_id=ds.id, version_number=2)
        v2.file_count = 3
        v2.total_size_bytes = 2048
        ds.versions = [v1, v2]

        resp = _build_dataset_response(ds)
        assert resp.total_file_count == 8
        assert resp.total_size_bytes == 3072
        assert resp.version_count == 2
        assert resp.created_by_name is None

    def test_build_dataset_response_with_user_name(self):
        from app.api.endpoints.datasets import _build_dataset_response

        ds = _make_dataset()
        ds.versions = []
        user_map = {ds.created_by: "testuser"}

        resp = _build_dataset_response(ds, user_map)
        assert resp.created_by_name == "testuser"

    def test_build_dataset_response_no_versions(self):
        from app.api.endpoints.datasets import _build_dataset_response

        ds = _make_dataset()
        ds.versions = []

        resp = _build_dataset_response(ds)
        assert resp.total_file_count == 0
        assert resp.total_size_bytes == 0
        assert resp.version_count == 0
        assert resp.latest_version is None


class TestDeleteDataset:
    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_delete_dataset_success(self, mock_to_thread, service, mock_db, mock_minio):
        dataset = _make_dataset()
        mock_db.execute.return_value = _sync_result(dataset)
        mock_db.delete = AsyncMock()

        mock_to_thread.side_effect = [[{"object_name": "obj1"}], None]

        await service.delete_dataset(dataset.id, dataset.tenant_id)

        mock_db.delete.assert_called_once_with(dataset)
        mock_db.flush.assert_called()

    async def test_delete_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.delete_dataset(uuid.uuid4(), uuid.uuid4())

    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_delete_with_audit(self, mock_to_thread, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.return_value = _sync_result(dataset)
        mock_db.delete = AsyncMock()
        mock_to_thread.return_value = []

        with patch("app.services.dataset_service.AuditService") as mock_audit_cls:
            mock_audit = AsyncMock()
            mock_audit_cls.return_value = mock_audit

            await service.delete_dataset(
                dataset.id,
                dataset.tenant_id,
                audit_context={"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"},
            )

            mock_audit.log_action.assert_called_once()


class TestDeleteVersion:
    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_delete_version_success(self, mock_to_thread, service, mock_db, mock_minio):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(version)]
        mock_db.delete = AsyncMock()

        mock_to_thread.side_effect = [[{"object_name": f"datasets/{dataset.id}/v1/file.csv"}], None]

        await service.delete_version(dataset.id, version.id, dataset.tenant_id)

        mock_db.delete.assert_called_once_with(version)
        mock_db.flush.assert_called()

    async def test_delete_version_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.delete_version(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    async def test_delete_version_not_found(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(None)]

        with pytest.raises(NotFoundException, match="数据集版本不存在"):
            await service.delete_version(dataset.id, uuid.uuid4(), dataset.tenant_id)

    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_delete_version_no_objects(self, mock_to_thread, service, mock_db, mock_minio):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(version)]
        mock_db.delete = AsyncMock()
        mock_to_thread.return_value = []

        await service.delete_version(dataset.id, version.id, dataset.tenant_id)

        mock_db.delete.assert_called_once_with(version)

    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_delete_version_with_audit(self, mock_to_thread, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=2)
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(version)]
        mock_db.delete = AsyncMock()
        mock_to_thread.return_value = []

        with patch("app.services.dataset_service.AuditService") as mock_audit_cls:
            mock_audit = AsyncMock()
            mock_audit_cls.return_value = mock_audit

            await service.delete_version(
                dataset.id,
                version.id,
                dataset.tenant_id,
                audit_context={"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"},
            )

            mock_audit.log_action.assert_called_once()


class TestListVersionFiles:
    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_list_version_files_success(self, mock_to_thread, service, mock_db, mock_minio):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=2)
        dataset.versions = [version]
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(version)]

        prefix = f"datasets/{dataset.id}/v2/"
        mock_to_thread.return_value = [
            {
                "object_name": f"{prefix}data.csv",
                "size": 1024,
                "content_type": "text/csv",
                "last_modified": _NOW,
            },
            {
                "object_name": f"{prefix}image.png",
                "size": 2048,
                "content_type": "image/png",
                "last_modified": _NOW,
            },
        ]

        files = await service.list_version_files(dataset.id, version.id, dataset.tenant_id)

        assert len(files) == 2
        assert files[0]["file_name"] == "data.csv"
        assert files[0]["size_bytes"] == 1024
        assert files[1]["file_name"] == "image.png"
        assert files[1]["size_bytes"] == 2048

    async def test_list_version_files_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.list_version_files(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    async def test_list_version_files_version_not_found(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(None)]

        with pytest.raises(NotFoundException, match="数据集版本不存在"):
            await service.list_version_files(dataset.id, uuid.uuid4(), dataset.tenant_id)

    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_list_version_files_empty(self, mock_to_thread, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        dataset.versions = [version]
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(version)]
        mock_to_thread.return_value = []

        files = await service.list_version_files(dataset.id, version.id, dataset.tenant_id)

        assert files == []


class TestGetVersionStats:
    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_get_version_stats_success(self, mock_to_thread, service, mock_db, mock_minio):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        dataset.versions = [version]
        mock_db.execute.side_effect = [
            _sync_result(dataset),
            _sync_result(version),
            _sync_result(dataset),
            _sync_result(version),
        ]
        prefix = f"datasets/{dataset.id}/v1/"
        mock_to_thread.return_value = [
            {
                "object_name": f"{prefix}data.csv",
                "size": 100,
                "content_type": "text/csv",
                "last_modified": _NOW,
            },
            {
                "object_name": f"{prefix}config.json",
                "size": 200,
                "content_type": "application/json",
                "last_modified": _NOW,
            },
            {
                "object_name": f"{prefix}report.csv",
                "size": 300,
                "content_type": "text/csv",
                "last_modified": _NOW,
            },
        ]

        stats = await service.get_version_stats(dataset.id, version.id, dataset.tenant_id)

        assert stats["version_id"] == str(version.id)
        assert stats["version_number"] == 1
        assert stats["file_count"] == 3
        assert stats["total_size_bytes"] == 600

        distribution = stats["file_type_distribution"]
        assert len(distribution) == 2
        csv_dist = next(d for d in distribution if d["extension"] == ".csv")
        assert csv_dist["count"] == 2
        assert csv_dist["total_size_bytes"] == 400
        json_dist = next(d for d in distribution if d["extension"] == ".json")
        assert json_dist["count"] == 1
        assert json_dist["total_size_bytes"] == 200

    async def test_get_version_stats_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.get_version_stats(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


class TestGetFileDownloadUrl:
    @patch("app.services.dataset_service.asyncio.to_thread", new_callable=AsyncMock)
    async def test_get_download_url_success(self, mock_to_thread, service, mock_db, mock_minio):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=3)
        dataset.versions = [version]
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(version)]
        mock_to_thread.return_value = "https://minio.example.com/presigned-url"

        url = await service.get_file_download_url(dataset.id, version.id, "data.csv", dataset.tenant_id)

        assert url == "https://minio.example.com/presigned-url"
        mock_to_thread.assert_called_once_with(
            mock_minio.presigned_get_url,
            dataset.tenant_id,
            f"datasets/{dataset.id}/v3/data.csv",
        )

    async def test_get_download_url_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.get_file_download_url(uuid.uuid4(), uuid.uuid4(), "file.txt", uuid.uuid4())

    async def test_download_url_version_not_found(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [_sync_result(dataset), _sync_result(None)]

        with pytest.raises(NotFoundException, match="数据集版本不存在"):
            await service.get_file_download_url(dataset.id, uuid.uuid4(), "file.txt", dataset.tenant_id)


class TestComputeFileTypeDistribution:
    def test_distribution_basic(self, service):
        files = [
            {"file_name": "a.csv", "size_bytes": 100},
            {"file_name": "b.csv", "size_bytes": 200},
            {"file_name": "c.json", "size_bytes": 50},
        ]
        result = service._compute_file_type_distribution(files)

        assert len(result) == 2
        assert result[0]["extension"] == ".csv"
        assert result[0]["count"] == 2
        assert result[0]["total_size_bytes"] == 300
        assert result[1]["extension"] == ".json"

    def test_distribution_no_extension(self, service):
        files = [{"file_name": "README", "size_bytes": 10}]
        result = service._compute_file_type_distribution(files)

        assert len(result) == 1
        assert result[0]["extension"] == "(无扩展名)"
        assert result[0]["count"] == 1

    def test_distribution_empty(self, service):
        result = service._compute_file_type_distribution([])
        assert result == []
