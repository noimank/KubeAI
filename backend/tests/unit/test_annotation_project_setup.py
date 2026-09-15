import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.sql.dml import Update

from app.core.exceptions import ConflictException, ExternalServiceException
from app.models.annotation import AnnotationProject
from app.models.annotation_template import AnnotationTemplate
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AnnotationProjectStatus
from app.services.annotation_service import AnnotationService

_LABEL_CONFIG = """<View>
  <Image name="image" value="$image"/>
  <Choices name="choice" toName="image">
    <Choice value="cat"/>
  </Choices>
</View>"""


def _make_project(status="pending"):
    project = AnnotationProject(
        name="test-project",
        label_config=_LABEL_CONFIG,
        total_tasks=0,
        completed_tasks=0,
        status=status,
        tenant_id=uuid.uuid4(),
        dataset_id=uuid.uuid4(),
        dataset_version_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
    )
    project.id = uuid.uuid4()
    dataset = Dataset(name="test-dataset", tenant_id=project.tenant_id, created_by=uuid.uuid4())
    dataset.id = project.dataset_id
    project.dataset = dataset
    version = DatasetVersion(
        dataset_id=project.dataset_id,
        version_number=1,
        storage_path="datasets/test-dataset/v1/",
        created_by=uuid.uuid4(),
    )
    version.id = project.dataset_version_id
    project.dataset_version = version
    return project


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    return db


def _setup_for_setup_flow(mock_db, project):
    mock_db.execute = AsyncMock(return_value=_sync_result(project))
    svc = AnnotationService(mock_db)
    svc._get_tenant_name = AsyncMock(return_value="default-tenant")
    svc.storage = MagicMock()
    svc.storage.list_files = AsyncMock(return_value=[{"file_name": "a.jpg"}])
    return svc


def _captured_update(mock_db):
    return [c.args[0] for c in mock_db.execute.await_args_list if isinstance(c.args[0], Update)]


class TestExecuteProjectSetup:
    async def test_skips_non_pending_project(self, mock_db):
        project = _make_project(status="active")
        svc = _setup_for_setup_flow(mock_db, project)

        await svc.execute_project_setup(project.id, project.tenant_id)

        mock_db.commit.assert_not_awaited()

    async def test_marks_failed_on_prepare_error_with_fresh_transaction(self, mock_db):
        project = _make_project(status="pending")
        svc = _setup_for_setup_flow(mock_db, project)
        svc._prepare_task_data = AsyncMock(side_effect=ExternalServiceException("解析失败"))

        with pytest.raises(ExternalServiceException):
            await svc.execute_project_setup(project.id, project.tenant_id)

        # 失败落库走独立事务: rollback → UPDATE → commit
        mock_db.rollback.assert_awaited_once()
        updates = _captured_update(mock_db)
        assert len(updates) == 1
        assert updates[0].compile().params["status"] == AnnotationProjectStatus.FAILED
        mock_db.commit.assert_awaited_once()

    async def test_success_sets_active(self, mock_db):
        project = _make_project(status="pending")
        svc = _setup_for_setup_flow(mock_db, project)
        svc._prepare_task_data = AsyncMock(return_value=[{"image": "x", "kubeai_object_name": "datasets/t/d/v1/a.jpg"}])

        await svc.execute_project_setup(project.id, project.tenant_id)

        assert project.status == AnnotationProjectStatus.ACTIVE
        assert project.total_tasks == 1
        mock_db.add_all.assert_called_once()
        mock_db.rollback.assert_not_awaited()
        mock_db.commit.assert_awaited_once()


class TestRetryProject:
    async def test_rejects_non_failed_project(self, mock_db):
        project = _make_project(status="active")
        mock_db.execute = AsyncMock(return_value=_sync_result(project))
        svc = AnnotationService(mock_db)

        with pytest.raises(ConflictException):
            await svc.retry_project(project.id, project.tenant_id)

        mock_db.commit.assert_not_awaited()

    async def test_retry_resets_state(self, mock_db):
        project = _make_project(status="failed")
        project.total_tasks = 5
        project.completed_tasks = 2
        mock_db.execute = AsyncMock(return_value=_sync_result(project))
        svc = AnnotationService(mock_db)

        result = await svc.retry_project(project.id, project.tenant_id)

        assert result.status == AnnotationProjectStatus.PENDING
        assert result.total_tasks == 0
        assert result.completed_tasks == 0
        mock_db.commit.assert_awaited_once()


class TestCreateProject:
    async def test_returns_project_with_template_loaded(self, mock_db):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        dataset = Dataset(name="d1", tenant_id=tenant_id, created_by=user_id)
        version = DatasetVersion(dataset_id=dataset.id, version_number=1, storage_path="/tmp", created_by=user_id)
        template = AnnotationTemplate(user_id=user_id, name="tpl", label_config=_LABEL_CONFIG, tenant_id=tenant_id)
        mock_db.execute = AsyncMock(side_effect=[_sync_result(dataset), _sync_result(version), _sync_result(template)])
        svc = AnnotationService(mock_db)

        project = await svc.create_project(
            tenant_id=tenant_id,
            user_id=user_id,
            name="p1",
            description=None,
            dataset_id=dataset.id,
            dataset_version_id=version.id,
            template_id=template.id,
        )

        assert project.template is template
        assert project.status == AnnotationProjectStatus.PENDING
