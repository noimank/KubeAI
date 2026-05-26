import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ExternalServiceException, ForbiddenException, NotFoundException
from app.models.annotation import AnnotationProject
from app.models.dataset import Dataset, DatasetVersion
from app.services.annotation_service import AnnotationService


def _make_project(
    total_tasks=10,
    completed_tasks=9,
    callback_status="pending",
    callback_error=None,
    status="active",
    ls_project_id=42,
):
    project = AnnotationProject(
        name="test-project",
        annotation_type="image_classification",
        label_config="<View></View>",
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        status=status,
        tenant_id=uuid.uuid4(),
        dataset_id=uuid.uuid4(),
        dataset_version_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    project.id = uuid.uuid4()
    project.callback_status = callback_status
    project.callback_error = callback_error
    project.callback_progress = 0
    project.callback_version_id = None

    dataset = Dataset(
        name="test-dataset",
        tenant_id=project.tenant_id,
        created_by=uuid.uuid4(),
    )
    dataset.id = project.dataset_id
    project.dataset = dataset

    version = DatasetVersion(
        dataset_id=project.dataset_id,
        version_number=1,
        storage_path="datasets/test-dataset/v1/",
        file_count=10,
        total_size_bytes=1024,
        created_by=uuid.uuid4(),
    )
    version.id = project.dataset_version_id
    project.dataset_version = version

    project.label_studio_project_id = ls_project_id
    return project


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_ls():
    ls = MagicMock()
    ls.export_project_annotations = AsyncMock(return_value=[{"id": 1, "data": {"image": "img.jpg"}, "annotations": []}])
    ls.create_annotation = AsyncMock(return_value={"id": 1})
    return ls


@pytest.fixture
def service(mock_db, mock_ls):
    svc = AnnotationService(mock_db, mock_ls)
    svc._get_tenant_name = AsyncMock(return_value="default-tenant")
    return svc


class TestAutoTriggerCallback:
    async def test_callback_triggered_when_all_tasks_complete(self, service, mock_db, mock_ls):
        """When all tasks are completed, trigger_callback should be called automatically."""
        project = _make_project(total_tasks=2, completed_tasks=1, callback_status="pending")
        tenant_id = project.tenant_id
        user_id = uuid.uuid4()

        from app.models.annotation_task import AnnotationTask

        task = AnnotationTask(
            project_id=project.id,
            label_studio_task_id=100,
            data={"image": "test.jpg"},
            assigned_to=user_id,
            status="in_progress",
            tenant_id=tenant_id,
        )
        task.id = uuid.uuid4()
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        with patch.object(service, "_trigger_callback", new_callable=AsyncMock) as mock_callback:
            await service.submit_annotation(
                task.id,
                tenant_id,
                user_id,
                result=[{"from_name": "choice", "to_name": "image", "type": "choices", "value": {"choices": ["cat"]}}],
            )
            mock_callback.assert_called_once_with(project, tenant_id)

    async def test_callback_not_triggered_when_tasks_remain(self, service, mock_db, mock_ls):
        """When tasks remain incomplete, callback should NOT be triggered."""
        project = _make_project(total_tasks=10, completed_tasks=8, callback_status="pending")
        tenant_id = project.tenant_id
        user_id = uuid.uuid4()

        from app.models.annotation_task import AnnotationTask

        task = AnnotationTask(
            project_id=project.id,
            label_studio_task_id=100,
            data={"image": "test.jpg"},
            assigned_to=user_id,
            status="in_progress",
            tenant_id=tenant_id,
        )
        task.id = uuid.uuid4()
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        with patch.object(service, "_trigger_callback", new_callable=AsyncMock) as mock_callback:
            await service.submit_annotation(
                task.id,
                tenant_id,
                user_id,
                result=[{"from_name": "choice", "to_name": "image", "type": "choices", "value": {"choices": ["cat"]}}],
            )
            mock_callback.assert_not_called()

    async def test_callback_failure_does_not_block_submit(self, service, mock_db, mock_ls):
        """When callback fails, submit should still succeed."""
        project = _make_project(total_tasks=2, completed_tasks=1, callback_status="pending")
        tenant_id = project.tenant_id
        user_id = uuid.uuid4()

        from app.models.annotation_task import AnnotationTask

        task = AnnotationTask(
            project_id=project.id,
            label_studio_task_id=100,
            data={"image": "test.jpg"},
            assigned_to=user_id,
            status="in_progress",
            tenant_id=tenant_id,
        )
        task.id = uuid.uuid4()
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        with patch.object(
            service, "_trigger_callback", new_callable=AsyncMock, side_effect=Exception("LabelStudio down")
        ):
            result = await service.submit_annotation(
                task.id,
                tenant_id,
                user_id,
                result=[{"from_name": "choice", "to_name": "image", "type": "choices", "value": {"choices": ["cat"]}}],
            )
            assert result.status == "completed"


class TestTriggerCallback:
    async def test_callback_success(self, service, mock_db, mock_ls):
        """Full successful callback flow."""
        project = _make_project(total_tasks=2, completed_tasks=2)
        tenant_id = project.tenant_id

        new_version = DatasetVersion(
            dataset_id=project.dataset_id,
            version_number=2,
            storage_path="datasets/test-dataset/v2/",
            file_count=0,
            total_size_bytes=0,
            created_by=project.created_by,
        )
        new_version.id = uuid.uuid4()

        mock_ds = MagicMock()
        mock_ds.create_version = AsyncMock(return_value=new_version)

        with (
            patch("app.services.dataset_service.DatasetService", return_value=mock_ds),
            patch.object(service.storage, "copy_file", new_callable=AsyncMock),
            patch.object(service.storage, "write_file", new_callable=AsyncMock),
            patch.object(service.storage, "list_files", new_callable=AsyncMock, return_value=[]),
        ):
            await service._trigger_callback(project, tenant_id)

        assert project.callback_status == "succeeded"
        assert project.callback_progress == 100
        assert project.callback_version_id == new_version.id
        assert project.status == "completed"
        mock_ls.export_project_annotations.assert_called_once_with(42)

    async def test_callback_fails_on_labelstudio_error(self, service, mock_db, mock_ls):
        """When LabelStudio export fails, callback should be marked as failed."""
        project = _make_project(total_tasks=2, completed_tasks=2)
        tenant_id = project.tenant_id

        mock_ls.export_project_annotations = AsyncMock(side_effect=ExternalServiceException("LabelStudio 不可用"))

        with pytest.raises(ExternalServiceException, match="LabelStudio"):
            await service._trigger_callback(project, tenant_id)

        assert project.callback_status == "failed"
        assert project.callback_error is not None
        assert "LabelStudio" in project.callback_error

    async def test_callback_rejects_non_active_project(self, service, mock_db):
        """Callback should reject projects that are not active."""
        project = _make_project(status="completed")
        tenant_id = project.tenant_id

        with pytest.raises(ForbiddenException, match="活跃"):
            await service._trigger_callback(project, tenant_id)

    async def test_callback_rejects_incomplete_tasks(self, service, mock_db):
        """Callback should reject when tasks are not fully completed."""
        project = _make_project(total_tasks=10, completed_tasks=5)
        tenant_id = project.tenant_id

        with pytest.raises(ForbiddenException, match="全部完成"):
            await service._trigger_callback(project, tenant_id)


class TestRetryCallback:
    async def test_retry_callback_success(self, service, mock_db):
        """Retry should reset status and re-trigger callback."""
        project = _make_project(callback_status="failed", callback_error="previous error")
        tenant_id = project.tenant_id
        user_id = uuid.uuid4()

        mock_db.execute = AsyncMock(return_value=_sync_result(project))

        with patch.object(service, "_trigger_callback", new_callable=AsyncMock) as mock_callback:
            await service.retry_callback(project.id, tenant_id, user_id)

            assert project.callback_status == "pending"
            assert project.callback_error is None
            assert project.callback_progress == 0
            mock_callback.assert_called_once_with(project, tenant_id)

    async def test_retry_rejects_non_failed_status(self, service, mock_db):
        """Retry should only work for failed callbacks."""
        project = _make_project(callback_status="succeeded")
        tenant_id = project.tenant_id

        mock_db.execute = AsyncMock(return_value=_sync_result(project))

        with pytest.raises(ForbiddenException, match="失败"):
            await service.retry_callback(project.id, tenant_id, uuid.uuid4())

    async def test_retry_project_not_found(self, service, mock_db):
        """Retry should raise NotFoundException for non-existent project."""
        mock_db.execute = AsyncMock(return_value=_sync_result(None))

        with pytest.raises(NotFoundException, match="标注项目不存在"):
            await service.retry_callback(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
