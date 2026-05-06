import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, NotFoundException
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
