import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
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


def _make_task(
    project_id=None,
    tenant_id=None,
    assigned_to=None,
    status="assigned",
    ls_task_id=100,
    kubeai_object_name="datasets/default-tenant/test-dataset/v1/img.jpg",
):
    task = AnnotationTask(
        project_id=project_id or uuid.uuid4(),
        label_studio_task_id=ls_task_id,
        kubeai_object_name=kubeai_object_name,
        data={"image": "/data/kubeai/datasets/test-tenant/test-dataset/v1/img.jpg"},
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
    return ls


@pytest.fixture
def service(mock_db, mock_ls):
    svc = AnnotationService(mock_db, mock_ls)
    svc._get_tenant_name = AsyncMock(return_value="default-tenant")
    svc.storage = MagicMock()
    svc.storage.write_file = AsyncMock()
    svc.storage.delete_file = AsyncMock(return_value=True)
    svc.storage.get_file_path = MagicMock(side_effect=lambda tn, dn, vn, fn: Path(f"/fake/{tn}/{dn}/v{vn}/{fn}"))
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

        result_payload = [{"from_name": "choice", "to_name": "image", "type": "choices", "value": {"choices": ["cat"]}}]
        result = await service.submit_annotation(
            task.id,
            tenant_id,
            user_id,
            result=result_payload,
        )

        assert result.status == "completed"
        assert project.completed_tasks == 1
        mock_ls.create_annotation.assert_called_once()

        # Per-file JSON write assertions
        assert service.storage.write_file.await_count == 1
        path_arg, bytes_arg = service.storage.write_file.call_args.args
        path_str = str(path_arg).replace("\\", "/")
        assert path_str.endswith("annotations/img.jpg.json")
        written = json.loads(bytes_arg.decode("utf-8"))
        assert written["task_id"] == str(task.id)
        assert written["annotation_project_id"] == str(project.id)
        assert written["result"] == result_payload

    async def test_submit_annotation_completes_project(self, service, mock_db):
        """Last task submission flips project.status to 'completed'."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        project.completed_tasks = 9  # total_tasks=10 in _make_project
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=user_id,
            status="in_progress",
        )
        task.project = project
        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        await service.submit_annotation(task.id, tenant_id, user_id, result=[])

        assert project.completed_tasks == 10
        assert project.status == "completed"

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


class TestCancelAnnotation:
    async def test_cancel_by_non_assignee_forbidden(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=uuid.uuid4(),  # not user_id
            status="completed",
        )
        task.project = project
        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        with pytest.raises(ForbiddenException, match="分配给自己"):
            await service.cancel_annotation(task.id, tenant_id, user_id)

    async def test_cancel_in_progress_forbidden(self, service, mock_db):
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

        with pytest.raises(ForbiddenException, match="已完成"):
            await service.cancel_annotation(task.id, tenant_id, user_id)

    async def test_cancel_completed_succeeds_and_decrements_counter(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        project.completed_tasks = 5
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=user_id,
            status="completed",
        )
        task.project = project
        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        result = await service.cancel_annotation(task.id, tenant_id, user_id)

        assert result.status == "in_progress"
        assert project.completed_tasks == 4
        service.storage.delete_file.assert_called_once()
        delete_path = service.storage.delete_file.call_args.args[3]
        assert delete_path == "annotations/img.jpg.json"

    async def test_cancel_last_completed_un_completes_project(self, service, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project = _make_project(tenant_id=tenant_id)
        project.status = "completed"
        project.completed_tasks = 10
        task = _make_task(
            project_id=project.id,
            tenant_id=tenant_id,
            assigned_to=user_id,
            status="completed",
        )
        task.project = project
        mock_db.execute = AsyncMock(return_value=_sync_result(task))

        await service.cancel_annotation(task.id, tenant_id, user_id)

        assert project.status == "active"
        assert project.completed_tasks == 9

    async def test_cancel_missing_file_is_idempotent(self, service, mock_db):
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
        service.storage.delete_file = AsyncMock(return_value=False)

        # Should not raise even though file doesn't exist
        result = await service.cancel_annotation(task.id, tenant_id, user_id)
        assert result.status == "in_progress"


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
