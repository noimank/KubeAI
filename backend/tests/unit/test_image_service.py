import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models.enums import BuildStatus
from app.models.image import Image
from app.services.image_service import ImageService


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


_NOW = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)


def _make_image(**overrides):
    defaults = {
        "name": "PyTorch 2.1",
        "tag": "2.1.0-cuda12.1",
        "image_ref": "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
        "source": "preset",
        "is_enabled": True,
    }
    defaults.update(overrides)
    img = Image(**defaults)
    img.id = uuid.uuid4()
    img.created_at = _NOW
    img.updated_at = _NOW
    img.deleted_at = None
    return img


def _make_custom_image(**overrides):
    tenant_id = overrides.pop("tenant_id", uuid.uuid4())
    defaults = {
        "name": "my-custom",
        "tag": "v1.0",
        "image_ref": "harbor.local/kubeai-test/my-custom:v1.0",
        "source": "custom",
        "is_enabled": True,
        "tenant_id": tenant_id,
        "build_status": BuildStatus.SUCCEEDED,
        "dockerfile": "FROM python:3.12\nRUN pip install numpy",
        "build_job_name": "image-build-abcdef12",
    }
    defaults.update(overrides)
    img = Image(**defaults)
    img.id = uuid.uuid4()
    img.created_at = _NOW
    img.updated_at = _NOW
    img.deleted_at = None
    return img


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return ImageService(mock_db)


class TestListImages:
    async def test_list_empty(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        items, total = await service.list_images()
        assert items == []
        assert total == 0

    async def test_list_with_keyword(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        await service.list_images(keyword="pytorch")
        assert mock_db.execute.call_count == 2

    async def test_list_with_source_filter(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        await service.list_images(source="preset")
        assert mock_db.execute.call_count == 2

    async def test_list_with_tenant_filter(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, rows_result]

        tenant_id = uuid.uuid4()
        await service.list_images(tenant_id=tenant_id)
        assert mock_db.execute.call_count == 2


class TestGetImage:
    async def test_get_image_found(self, service, mock_db):
        image = _make_image()
        mock_db.execute.return_value = _sync_result(image)

        result = await service.get_image(image.id)
        assert result.name == "PyTorch 2.1"

    async def test_get_image_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="镜像不存在"):
            await service.get_image(uuid.uuid4())


class TestCreateImage:
    async def test_create_image_success(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        result = await service.create_image(
            name="PyTorch 2.1",
            tag="2.1.0-cuda12.1",
            image_ref="pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
        )

        assert result.name == "PyTorch 2.1"
        assert result.source == "preset"
        assert result.is_enabled is True
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_create_image_duplicate_ref(self, service, mock_db):
        existing = _make_image()
        mock_db.execute.return_value = _sync_result(existing)

        with pytest.raises(ConflictException, match="镜像地址已存在"):
            await service.create_image(
                name="Duplicate",
                tag="1.0",
                image_ref="pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
            )

    async def test_create_image_with_audit(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with patch("app.services.image_service.AuditService") as mock_audit_cls:
            mock_audit = AsyncMock()
            mock_audit_cls.return_value = mock_audit

            await service.create_image(
                name="Test",
                tag="1.0",
                image_ref="test/img:1.0",
                audit_context={"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"},
            )

            mock_audit.log_action.assert_called_once()


class TestUpdateImage:
    async def test_update_image_success(self, service, mock_db):
        image = _make_image()
        mock_db.execute.side_effect = [_sync_result(image)]

        result = await service.update_image(
            image_id=image.id,
            name="Updated Name",
        )

        assert result.name == "Updated Name"
        mock_db.flush.assert_called()

    async def test_update_image_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="镜像不存在"):
            await service.update_image(
                image_id=uuid.uuid4(),
                name="New Name",
            )

    async def test_update_image_duplicate_ref(self, service, mock_db):
        image = _make_image()
        other = _make_image(image_ref="other/img:1.0")
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(other)]

        with pytest.raises(ConflictException, match="镜像地址已存在"):
            await service.update_image(
                image_id=image.id,
                image_ref="other/img:1.0",
            )

    async def test_update_image_with_audit(self, service, mock_db):
        image = _make_image()
        mock_db.execute.side_effect = [_sync_result(image)]

        with patch("app.services.image_service.AuditService") as mock_audit_cls:
            mock_audit = AsyncMock()
            mock_audit_cls.return_value = mock_audit

            await service.update_image(
                image_id=image.id,
                audit_context={"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"},
                name="Updated",
            )

            mock_audit.log_action.assert_called_once()


class TestDeleteImage:
    async def test_delete_image_success(self, service, mock_db):
        image = _make_image()
        mock_db.execute.return_value = _sync_result(image)

        await service.delete_image(image.id)

        assert image.deleted_at is not None
        mock_db.flush.assert_called()

    async def test_delete_image_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="镜像不存在"):
            await service.delete_image(uuid.uuid4())

    async def test_delete_image_with_audit(self, service, mock_db):
        image = _make_image()
        mock_db.execute.return_value = _sync_result(image)

        with patch("app.services.image_service.AuditService") as mock_audit_cls:
            mock_audit = AsyncMock()
            mock_audit_cls.return_value = mock_audit

            await service.delete_image(
                image.id,
                audit_context={"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"},
            )

            mock_audit.log_action.assert_called_once()


class TestToggleImage:
    async def test_toggle_enable_to_disable(self, service, mock_db):
        image = _make_image(is_enabled=True)
        mock_db.execute.return_value = _sync_result(image)

        result = await service.toggle_image(image.id)

        assert result.is_enabled is False
        mock_db.flush.assert_called()

    async def test_toggle_disable_to_enable(self, service, mock_db):
        image = _make_image(is_enabled=False)
        mock_db.execute.return_value = _sync_result(image)

        result = await service.toggle_image(image.id)

        assert result.is_enabled is True

    async def test_toggle_image_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="镜像不存在"):
            await service.toggle_image(uuid.uuid4())

    async def test_toggle_image_with_audit(self, service, mock_db):
        image = _make_image(is_enabled=True)
        mock_db.execute.return_value = _sync_result(image)

        with patch("app.services.image_service.AuditService") as mock_audit_cls:
            mock_audit = AsyncMock()
            mock_audit_cls.return_value = mock_audit

            await service.toggle_image(
                image.id,
                audit_context={"user_id": uuid.uuid4(), "ip_address": "127.0.0.1"},
            )

            mock_audit.log_action.assert_called_once()


class TestBuildImage:
    @patch("app.services.image_service.k8s_secret")
    @patch("app.services.image_service.k8s_job")
    @patch("app.services.image_service.harbor_client")
    async def test_build_image_success(self, mock_harbor, mock_job, mock_secret, service, mock_db):
        mock_harbor.ensure_project.return_value = {"name": "kubeai-test"}
        mock_harbor.make_harbor_dockerconfig.return_value = {".dockerconfigjson": "{}"}
        mock_harbor.make_harbor_image_ref.return_value = "harbor.local/kubeai-test/my-img:v1"
        mock_job.make_job_name.return_value = "image-build-test"
        mock_job.make_configmap_name.return_value = "dockerfile-test"
        mock_job.create_configmap.return_value = MagicMock()
        mock_job.create_build_job.return_value = MagicMock()
        mock_job.submit_job.return_value = MagicMock()
        mock_secret.create_secret.return_value = MagicMock()

        tenant_id = uuid.uuid4()
        result = await service.build_image(
            dockerfile="FROM python:3.12",
            name="my-img",
            tag="v1",
            description="test",
            tenant_id=tenant_id,
        )

        assert result.source == "custom"
        assert result.build_status == BuildStatus.PENDING
        assert result.tenant_id == tenant_id
        assert result.is_enabled is False
        mock_harbor.ensure_project.assert_called_once()
        mock_job.submit_job.assert_called_once()

    async def test_build_image_empty_dockerfile(self, service, mock_db):
        with pytest.raises(BadRequestException, match="Dockerfile"):
            await service.build_image(
                dockerfile="   ",
                name="my-img",
                tag="v1",
                description="test",
                tenant_id=uuid.uuid4(),
            )

    @patch("app.services.image_service.k8s_job")
    @patch("app.services.image_service.harbor_client")
    async def test_build_image_k8s_failure_marks_failed(self, mock_harbor, mock_job, service, mock_db):
        mock_harbor.ensure_project.side_effect = Exception("K8s unavailable")

        tenant_id = uuid.uuid4()
        with pytest.raises(Exception, match="K8s unavailable"):
            await service.build_image(
                dockerfile="FROM python:3.12",
                name="my-img",
                tag="v1",
                description="test",
                tenant_id=tenant_id,
            )


class TestRebuildImage:
    async def test_rebuild_not_custom(self, service, mock_db):
        image = _make_image(source="preset")
        mock_db.execute.return_value = _sync_result(image)

        with pytest.raises(BadRequestException, match="仅自定义镜像"):
            await service.rebuild_image(image.id)

    async def test_rebuild_no_tenant(self, service, mock_db):
        image = _make_custom_image(source="custom", tenant_id=None, build_status=BuildStatus.FAILED)
        mock_db.execute.return_value = _sync_result(image)

        with pytest.raises(BadRequestException, match="缺少租户信息"):
            await service.rebuild_image(image.id)

    async def test_rebuild_wrong_status(self, service, mock_db):
        image = _make_custom_image(build_status=BuildStatus.BUILDING)
        mock_db.execute.return_value = _sync_result(image)

        with pytest.raises(BadRequestException, match="仅失败或已完成"):
            await service.rebuild_image(image.id)

    @patch("app.services.image_service.k8s_job")
    @patch("app.services.image_service.harbor_client")
    async def test_rebuild_success(self, mock_harbor, mock_job, service, mock_db):
        image = _make_custom_image(build_status=BuildStatus.FAILED)
        mock_db.execute.return_value = _sync_result(image)

        mock_job.make_job_name.return_value = "image-build-test"
        mock_job.make_configmap_name.return_value = "dockerfile-test"
        mock_job.create_configmap.return_value = MagicMock()
        mock_job.create_build_job.return_value = MagicMock()
        mock_job.submit_job.return_value = MagicMock()
        mock_harbor.make_harbor_image_ref.return_value = "harbor.local/kubeai-test/my-custom:v1.0"

        result = await service.rebuild_image(image.id)

        assert result.build_status == BuildStatus.PENDING
        assert result.is_enabled is False
        mock_job.submit_job.assert_called_once()


class TestGetBuildLog:
    @patch("app.services.image_service.k8s_job")
    async def test_get_build_log_success(self, mock_job, service, mock_db):
        image = _make_custom_image(build_status=BuildStatus.SUCCEEDED)
        mock_db.execute.return_value = _sync_result(image)
        mock_job.get_job_logs.return_value = "Step 1/5: FROM python:3.12\nStep 2/5: RUN pip install numpy"

        result = await service.get_build_log(image.id)
        assert "FROM python:3.12" in result

    async def test_get_build_log_no_job(self, service, mock_db):
        image = _make_image()
        mock_db.execute.return_value = _sync_result(image)

        result = await service.get_build_log(image.id)
        assert result == ""


class TestSyncBuildStatus:
    @patch("app.services.image_service.k8s_job")
    @patch("app.services.image_service.harbor_client")
    async def test_sync_to_succeeded(self, mock_harbor, mock_job, service, mock_db):
        tenant_id = uuid.uuid4()
        image = _make_custom_image(
            tenant_id=tenant_id,
            build_status=BuildStatus.BUILDING,
        )
        mock_job.get_job_status.return_value = {"status": "succeeded", "active": False}
        mock_harbor.make_harbor_image_ref.return_value = "harbor.local/kubeai-test/my-custom:v1.0"

        result = await service.sync_build_status(image)

        assert result.build_status == BuildStatus.SUCCEEDED
        assert result.is_enabled is True
        assert result.image_ref == "harbor.local/kubeai-test/my-custom:v1.0"

    @patch("app.services.image_service.k8s_job")
    async def test_sync_to_failed(self, mock_job, service, mock_db):
        image = _make_custom_image(build_status=BuildStatus.BUILDING)
        mock_job.get_job_status.return_value = {"status": "failed", "active": False}

        result = await service.sync_build_status(image)
        assert result.build_status == BuildStatus.FAILED

    @patch("app.services.image_service.k8s_job")
    async def test_sync_still_running(self, mock_job, service, mock_db):
        image = _make_custom_image(build_status=BuildStatus.PENDING)
        mock_job.get_job_status.return_value = {"status": "running", "active": True}

        result = await service.sync_build_status(image)
        assert result.build_status == BuildStatus.BUILDING

    async def test_sync_no_job_name(self, service, mock_db):
        image = _make_image()
        result = await service.sync_build_status(image)
        assert result == image

    async def test_sync_already_succeeded(self, service, mock_db):
        image = _make_custom_image(build_status=BuildStatus.SUCCEEDED)
        result = await service.sync_build_status(image)
        assert result == image


class TestListSelectableImages:
    async def test_returns_empty(self, service, mock_db):
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = rows_result

        result = await service.list_selectable_images(uuid.uuid4())
        assert result == []

    async def test_returns_enabled_preset_and_custom(self, service, mock_db):
        preset = _make_image(source="preset", is_enabled=True)
        preset.tenant_id = None
        tenant_id = uuid.uuid4()
        custom = _make_custom_image(tenant_id=tenant_id, is_enabled=True, build_status=BuildStatus.SUCCEEDED)

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [preset, custom]
        mock_db.execute.return_value = rows_result

        result = await service.list_selectable_images(tenant_id)
        assert len(result) == 2
        assert result[0].source == "preset"
        assert result[1].source == "custom"

    async def test_tenant_isolation(self, service, mock_db):
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = rows_result

        other_tenant = uuid.uuid4()
        await service.list_selectable_images(other_tenant)
        mock_db.execute.assert_called_once()

    async def test_excludes_disabled_images(self, service, mock_db):
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = rows_result

        await service.list_selectable_images(uuid.uuid4())
        mock_db.execute.assert_called_once()

    async def test_excludes_unsucceeded_custom_images(self, service, mock_db):
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = rows_result

        await service.list_selectable_images(uuid.uuid4())
        mock_db.execute.assert_called_once()
