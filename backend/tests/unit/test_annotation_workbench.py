import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.annotation import AnnotationProject
from app.models.annotation_task import AnnotationTask
from app.models.dataset import Dataset, DatasetVersion
from app.services.annotation_service import AnnotationService

_NOW = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)


def _make_project(
    annotation_type="image_classification",
    tenant_id=None,
    dataset_id=None,
    version_id=None,
):
    project = AnnotationProject(
        name="test-project",
        annotation_type=annotation_type,
        label_config="""<View>
  <Image name="image" value="$image"/>
  <Choices name="choice" toName="image">
    <Choice value="cat"/>
    <Choice value="dog"/>
  </Choices>
</View>""",
        total_tasks=10,
        completed_tasks=0,
        status="active",
        tenant_id=tenant_id or uuid.uuid4(),
        dataset_id=dataset_id or uuid.uuid4(),
        dataset_version_id=version_id or uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    project.id = uuid.uuid4()
    project.created_at = _NOW
    project.updated_at = _NOW
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
    return project


def _make_task(project_id=None, tenant_id=None, assigned_to=None, status="assigned", ls_task_id=100):
    task = AnnotationTask(
        project_id=project_id or uuid.uuid4(),
        label_studio_task_id=ls_task_id,
        data={"image": "https://minio.example.com/bucket/datasets/test-dataset/v1/img.jpg?X-Amz-Signature=abc"},
        assigned_to=assigned_to,
        status=status,
        tenant_id=tenant_id or uuid.uuid4(),
    )
    task.id = uuid.uuid4()
    task.created_at = _NOW
    task.updated_at = _NOW
    return task


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
    return db


@pytest.fixture
def mock_ls():
    ls = MagicMock()
    ls.create_annotation = AsyncMock(return_value={"id": 1})
    ls.list_annotations = AsyncMock(return_value=[])
    ls.delete_annotation = AsyncMock()
    return ls


@pytest.fixture
def mock_minio():
    m = MagicMock()
    m.presigned_get_url = AsyncMock(return_value="https://minio.example.com/fresh-presigned-url")
    return m


@pytest.fixture
def service(mock_db, mock_ls, mock_minio):
    svc = AnnotationService(mock_db, mock_ls, mock_minio)
    svc._get_tenant_name = AsyncMock(return_value="default-tenant")
    return svc


class TestStartAnnotation:
    async def test_start_annotation_success(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=user_id,
            status="assigned",
        )
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        result = await service.start_annotation(task.id, tenant_id, user_id)

        assert result.status == "in_progress"
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_start_annotation_wrong_user(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        other_user = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=other_user,
            status="assigned",
        )
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        with pytest.raises(ForbiddenException, match="分配给自己"):
            await service.start_annotation(task.id, tenant_id, user_id)

    async def test_start_annotation_wrong_status(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=user_id,
            status="completed",
        )
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        with pytest.raises(ForbiddenException, match="已分配"):
            await service.start_annotation(task.id, tenant_id, user_id)

    async def test_start_annotation_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=_sync_result(None))

        with pytest.raises(NotFoundException):
            await service.start_annotation(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


class TestSubmitAnnotation:
    async def test_submit_annotation_success(self, service, mock_db, mock_ls):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=user_id,
            status="in_progress",
        )
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        result = await service.submit_annotation(
            task.id,
            tenant_id,
            user_id,
            result=[{"from_name": "choice", "to_name": "image", "type": "choices", "value": {"choices": ["cat"]}}],
        )

        assert result.status == "completed"
        assert project.completed_tasks == 1
        mock_ls.create_annotation.assert_called_once()

    async def test_submit_annotation_not_in_progress(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=user_id,
            status="assigned",
        )
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        with pytest.raises(ForbiddenException, match="进行中"):
            await service.submit_annotation(task.id, tenant_id, user_id, result=[])


class TestGetNextTask:
    async def test_get_next_task_found(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=user_id,
            status="assigned",
        )
        task.project = project

        project_result = MagicMock()
        project_result.scalar_one_or_none.return_value = project
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        mock_db.execute = AsyncMock(side_effect=[project_result, task_result])

        result = await service.get_next_task(project.id, tenant_id, user_id)

        assert result is not None
        assert result.id == task.id

    async def test_get_next_task_none(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)

        project_result = MagicMock()
        project_result.scalar_one_or_none.return_value = project
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[project_result, task_result])

        result = await service.get_next_task(project.id, tenant_id, user_id)

        assert result is None


class TestGetTaskDetail:
    async def test_get_task_detail_success(self, service, mock_db):
        tenant_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            status="in_progress",
        )
        task.project = project

        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        result = await service.get_task_detail(task.id, tenant_id)

        assert result.id == task.id

    async def test_get_task_detail_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=_sync_result(None))

        with pytest.raises(NotFoundException):
            await service.get_task_detail(uuid.uuid4(), uuid.uuid4())
