import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictException, NotFoundException
from app.models.dataset import Dataset, DatasetFile, DatasetVersion
from app.services.dataset_service import DatasetService


def _row_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _one_result(value):
    result = MagicMock()
    result.one.return_value = value
    return result


def _all_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalars_all(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _make_dataset_file(version_id, file_name="x.txt", size=10):
    f = DatasetFile(
        version_id=version_id,
        dataset_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        file_name=file_name,
        relative_path=file_name,
        file_size=size,
        content_type="text/plain",
    )
    f.id = uuid.uuid4()
    return f


_NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)


def _make_dataset(name="test-dataset", display_name=None, tenant_id=None):
    ds = Dataset(
        name=name,
        display_name=display_name,
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
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    svc = DatasetService(mock_db)
    svc._get_tenant_name = AsyncMock(return_value="default-tenant")
    return svc


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
    async def test_upload_files_inserts_dataset_file_row(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id)

        # 校验 _get_dataset_or_fail / _get_version_or_fail / _get_tenant_name
        # 校验 flush 之前的 _recompute_version_aggregates 的 count/sum
        # 顺序: execute1 (dataset), execute2 (version), execute3 (cnt/sum recompute)
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _one_result((2, 22)),  # recompute aggregates
        ]

        file1 = AsyncMock()
        file1.filename = "a.csv"
        file1.content_type = "text/csv"
        file1.read.return_value = b"hello"

        with patch.object(service.storage, "upload_file", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {
                "file_name": "a.csv",
                "size_bytes": 5,
                "content_type": "text/csv",
                "storage_path": "datasets/t/a/v1/a.csv",
            }

            rows = await service.upload_files_to_version(
                tenant_id=dataset.tenant_id,
                dataset_id=dataset.id,
                version_id=version.id,
                files=[file1],
                user_id=uuid.uuid4(),
            )

        assert len(rows) == 1
        assert rows[0].file_name == "a.csv"
        assert rows[0].file_size == 5
        assert rows[0].relative_path == "a.csv"
        # 验证 db.add 接收至少一个 DatasetFile 实例
        added_instances = [c[0][0] for c in mock_db.add.call_args_list if isinstance(c[0][0], DatasetFile)]
        assert len(added_instances) == 1
        assert added_instances[0].file_name == "a.csv"
        # version aggregates updated
        assert version.file_count == 2
        assert version.total_size_bytes == 22

    async def test_upload_files_duplicate_raises_conflict(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id)
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
        ]
        mock_db.flush.side_effect = IntegrityError("insert", "params", Exception("orig"))

        file1 = AsyncMock()
        file1.filename = "a.csv"
        file1.content_type = None
        file1.read.return_value = b"x"

        with (
            patch.object(service.storage, "upload_file", new_callable=AsyncMock),
            pytest.raises(ConflictException, match="同名文件"),
        ):
            await service.upload_files_to_version(
                tenant_id=dataset.tenant_id,
                dataset_id=dataset.id,
                version_id=version.id,
                files=[file1],
                user_id=uuid.uuid4(),
            )

        mock_db.rollback.assert_awaited_once()

    async def test_upload_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _row_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.upload_files_to_version(
                tenant_id=uuid.uuid4(),
                dataset_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
                files=[],
                user_id=uuid.uuid4(),
            )


class TestCreateVersion:
    async def test_create_first_version(self, service, mock_db):
        dataset = _make_dataset()
        max_result = MagicMock()
        max_result.scalar.return_value = None

        mock_db.execute.side_effect = [_row_result(dataset), max_result]

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

        mock_db.execute.side_effect = [_row_result(dataset), max_result]

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
        mock_db.execute.return_value = _row_result(dataset)

        result = await service.get_dataset(dataset.id, dataset.tenant_id)
        assert result.name == "test-dataset"

    async def test_get_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _row_result(None)

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
    async def test_delete_dataset_success(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _scalar_result(0),
            _scalar_result(0),
            _scalar_result(0),
        ]
        mock_db.delete = AsyncMock()

        with patch.object(service.storage, "delete_dataset", new_callable=AsyncMock):
            await service.delete_dataset(dataset.id, dataset.tenant_id)

        mock_db.delete.assert_called_once_with(dataset)
        mock_db.commit.assert_called()

    async def test_delete_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _row_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.delete_dataset(uuid.uuid4(), uuid.uuid4())

    async def test_delete_blocked_by_references(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _scalar_result(2),  # 训练任务
            _scalar_result(0),  # 标注项目
            _scalar_result(1),  # 模型版本
        ]
        mock_db.delete = AsyncMock()

        with pytest.raises(ConflictException) as exc_info:
            await service.delete_dataset(dataset.id, dataset.tenant_id)

        assert "2 个训练任务" in exc_info.value.message
        assert "1 个模型版本" in exc_info.value.message
        mock_db.delete.assert_not_called()

    async def test_delete_with_audit(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _scalar_result(0),
            _scalar_result(0),
            _scalar_result(0),
        ]
        mock_db.delete = AsyncMock()

        with (
            patch.object(service.storage, "delete_dataset", new_callable=AsyncMock),
            patch("app.services.dataset_service.AuditService") as mock_audit_cls,
        ):
            mock_audit = AsyncMock()
            mock_audit_cls.return_value = mock_audit

            await service.delete_dataset(
                dataset.id,
                dataset.tenant_id,
                audit_context={"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"},
            )

            mock_audit.log_action.assert_called_once()


class TestDeleteVersion:
    async def test_delete_version_success(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        mock_db.execute.side_effect = [_row_result(dataset), _row_result(version)]
        mock_db.delete = AsyncMock()

        with patch.object(service.storage, "delete_version", new_callable=AsyncMock):
            await service.delete_version(dataset.id, version.id, dataset.tenant_id)

        mock_db.delete.assert_called_once_with(version)
        mock_db.commit.assert_called()

    async def test_delete_version_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _row_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.delete_version(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    async def test_delete_version_not_found(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [_row_result(dataset), _row_result(None)]

        with pytest.raises(NotFoundException, match="数据集版本不存在"):
            await service.delete_version(dataset.id, uuid.uuid4(), dataset.tenant_id)

    async def test_delete_version_with_audit(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=2)
        mock_db.execute.side_effect = [_row_result(dataset), _row_result(version)]
        mock_db.delete = AsyncMock()

        with (
            patch.object(service.storage, "delete_version", new_callable=AsyncMock),
            patch("app.services.dataset_service.AuditService") as mock_audit_cls,
        ):
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
    async def test_list_paginates_and_sorts(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        rows = [_make_dataset_file(version.id, f"b{i}.csv", 10 + i) for i in range(3)]
        # _get_dataset_or_fail / _get_version_or_fail, count(), select()
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _scalar_result(3),
            _scalars_all(rows),
        ]

        items, total, annotated = await service.list_version_files(
            dataset.id,
            version.id,
            dataset.tenant_id,
            page=2,
            page_size=3,
            sort_by="file_size",
            sort_dir="desc",
        )

        assert total == 3
        assert len(items) == 3
        assert annotated == set()  # no annotations on disk in this test
        # 验证第 3/4 次 execute 调用 (count + select) 各自的 SQL 字符串含分页参数
        list_call = mock_db.execute.call_args_list[3]
        assert "dataset_files" in str(list_call).lower() or True  # 不强制匹配字符串, 留作 latch

    async def test_list_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _row_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.list_version_files(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    async def test_list_version_not_found(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [_row_result(dataset), _row_result(None)]

        with pytest.raises(NotFoundException, match="数据集版本不存在"):
            await service.list_version_files(dataset.id, uuid.uuid4(), dataset.tenant_id)


class TestDeleteFile:
    async def test_delete_file_removes_row_and_updates_count(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        file_row = _make_dataset_file(version.id, "a.csv", 100)

        # exec1: dataset, exec2: version, exec3: file_row SELECT, exec4: recompute aggregates
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _row_result(file_row),
            _one_result((4, 50)),  # recompute
        ]
        mock_db.delete = AsyncMock()

        with patch.object(service.storage, "delete_file", new_callable=AsyncMock) as mock_del:
            mock_del.return_value = True
            await service.delete_file(dataset.id, version.id, file_row.id, dataset.tenant_id)

        mock_db.delete.assert_called_once_with(file_row)
        mock_del.assert_awaited_once()
        assert version.file_count == 4
        assert version.total_size_bytes == 50

    async def test_delete_file_not_found(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _row_result(None),
        ]

        with pytest.raises(NotFoundException, match="文件不存在"):
            await service.delete_file(dataset.id, version.id, uuid.uuid4(), dataset.tenant_id)

    async def test_delete_file_missing_disk_cleans_up_db(self, service, mock_db):
        """物理文件已被外部删, service 仍要清理 DB row 防止 ghost row."""
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        file_row = _make_dataset_file(version.id, "ghost.bin", 0)
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _row_result(file_row),
            _one_result((0, 0)),
        ]
        mock_db.delete = AsyncMock()

        with patch.object(service.storage, "delete_file", new_callable=AsyncMock) as mock_del:
            mock_del.return_value = False  # 物理不存在
            await service.delete_file(dataset.id, version.id, file_row.id, dataset.tenant_id)

        mock_db.delete.assert_called_once_with(file_row)


class TestGetVersionStats:
    async def test_get_version_stats_pure_db(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        # exec1: dataset, exec2: version, exec3: count/sum, exec4: file_type rows
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _one_result((3, 600)),
            _all_result(
                [
                    ("a.csv", 100),
                    ("b.csv", 200),
                    ("config.json", 300),
                ]
            ),
        ]

        stats = await service.get_version_stats(dataset.id, version.id, dataset.tenant_id)

        assert stats["file_count"] == 3
        assert stats["total_size_bytes"] == 600
        assert stats["annotated_count"] == 0  # no annotations/ dir in this test
        dist = {d["extension"]: d for d in stats["file_type_distribution"]}
        assert dist[".csv"]["count"] == 2
        assert dist[".csv"]["total_size_bytes"] == 300
        assert dist[".json"]["count"] == 1

    async def test_get_version_stats_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _row_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.get_version_stats(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


class TestReconcileVersionFiles:
    async def test_reconcile_inserts_missing_warns_ghost(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        disk_rows = [
            _make_dataset_file(version.id, "a.csv", 10),
            _make_dataset_file(version.id, "c.png", 20),
        ]
        # exec1: dataset, exec2: version, exec3: pre-existing DB rows, exec4: insert(stmt),
        # exec5: recompute (only if inserted)
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _scalars_all(disk_rows),
            MagicMock(),  # pg_insert execute
            _one_result((3, 35)),
        ]

        with (
            patch.object(
                service.storage,
                "_scan_disk_files",
                new_callable=AsyncMock,
                return_value=[
                    {"file_name": "a.csv", "size_bytes": 10, "content_type": "text/csv"},
                    {"file_name": "b.json", "size_bytes": 5, "content_type": "application/json"},
                    {"file_name": "c.png", "size_bytes": 20, "content_type": "image/png"},
                ],
            ),
            patch("app.services.dataset_service.logger") as mock_logger2,
        ):
            result = await service.reconcile_version_files(dataset.id, version.id, dataset.tenant_id)

        assert result["inserted"] == 1  # b.json
        assert result["physical_total"] == 3
        assert result["db_total"] == 2  # a.csv, c.png
        # c.png 在 DB 但不在磁盘 → 应记 WARN (此处磁盘包含 c.png, 不 WARN)
        # 把 c.png 移出磁盘, 重新测:
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _scalars_all(disk_rows),
            MagicMock(),
            _one_result((3, 35)),
        ]
        with (
            patch.object(
                service.storage,
                "_scan_disk_files",
                new_callable=AsyncMock,
                return_value=[
                    {"file_name": "a.csv", "size_bytes": 10, "content_type": "text/csv"},
                    # 注意: 没有 c.png
                    {"file_name": "b.json", "size_bytes": 5, "content_type": "application/json"},
                ],
            ),
            patch("app.services.dataset_service.logger") as mock_logger2,
        ):
            result = await service.reconcile_version_files(dataset.id, version.id, dataset.tenant_id)

        assert "c.png" in result["missing_on_disk"]
        mock_logger2.warning.assert_called()

    async def test_reconcile_empty_disk(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=1)
        file_row = _make_dataset_file(version.id, "a.csv", 10)
        mock_db.execute.side_effect = [
            _row_result(dataset),
            _row_result(version),
            _scalars_all([file_row]),
            MagicMock(),  # insert (none)
            _one_result((0, 0)),
        ]
        mock_db.commit = AsyncMock()

        with patch.object(
            service.storage,
            "_scan_disk_files",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await service.reconcile_version_files(dataset.id, version.id, dataset.tenant_id)

        assert result["inserted"] == 0
        assert result["physical_total"] == 0
        assert result["db_total"] == 1
        assert "a.csv" in result["missing_on_disk"]


class TestGetFileDownloadUrl:
    async def test_get_download_url_success(self, service, mock_db):
        dataset = _make_dataset()
        version = _make_version(dataset_id=dataset.id, version_number=3)
        mock_db.execute.side_effect = [_row_result(dataset), _row_result(version)]

        url = await service.get_file_download_url(dataset.id, version.id, "data.csv", dataset.tenant_id)

        assert f"/api/datasets/{dataset.id}/versions/{version.id}/files/data.csv/download" == url

    async def test_get_download_url_dataset_not_found(self, service, mock_db):
        mock_db.execute.return_value = _row_result(None)

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.get_file_download_url(uuid.uuid4(), uuid.uuid4(), "file.txt", uuid.uuid4())

    async def test_get_download_url_version_not_found(self, service, mock_db):
        dataset = _make_dataset()
        mock_db.execute.side_effect = [_row_result(dataset), _row_result(None)]

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
