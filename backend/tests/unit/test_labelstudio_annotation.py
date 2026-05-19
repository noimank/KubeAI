from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ExternalServiceException
from app.integrations.labelstudio.client import LabelStudioClient
from app.integrations.labelstudio.templates import get_annotation_result_template


@pytest.fixture
def mock_sdk():
    sdk = MagicMock()
    sdk.annotations = MagicMock()
    return sdk


@pytest.fixture
def ls_client(mock_sdk):
    client = LabelStudioClient.__new__(LabelStudioClient)
    client._sdk = mock_sdk
    return client


class TestCreateAnnotation:
    async def test_create_annotation_success(self, ls_client):
        annotation = MagicMock(id=1)
        ls_client._sdk.annotations.create = AsyncMock(return_value=annotation)

        result = await ls_client.create_annotation(
            42, [{"from_name": "choice", "to_name": "image", "type": "choices", "value": {"choices": ["cat"]}}]
        )

        ls_client._sdk.annotations.create.assert_awaited_once_with(
            id=42,
            result=[{"from_name": "choice", "to_name": "image", "type": "choices", "value": {"choices": ["cat"]}}],
        )
        assert result.id == 1

    async def test_create_annotation_failure(self, ls_client):
        ls_client._sdk.annotations.create = AsyncMock(side_effect=Exception("connection error"))

        with pytest.raises(ExternalServiceException, match="LabelStudio create_annotation"):
            await ls_client.create_annotation(42, [])


class TestListAnnotations:
    async def test_list_annotations_success(self, ls_client):
        annotations = [MagicMock(id=1), MagicMock(id=2)]
        ls_client._sdk.annotations.list = AsyncMock(return_value=annotations)

        result = await ls_client.list_annotations(42)

        ls_client._sdk.annotations.list.assert_awaited_once_with(id=42)
        assert len(result) == 2

    async def test_list_annotations_failure(self, ls_client):
        ls_client._sdk.annotations.list = AsyncMock(side_effect=Exception("timeout"))

        with pytest.raises(ExternalServiceException, match="LabelStudio list_annotations"):
            await ls_client.list_annotations(42)


class TestDeleteAnnotation:
    async def test_delete_annotation_success(self, ls_client):
        ls_client._sdk.annotations.delete = AsyncMock(return_value=None)

        await ls_client.delete_annotation(99)

        ls_client._sdk.annotations.delete.assert_awaited_once_with(id=99)

    async def test_delete_annotation_failure(self, ls_client):
        ls_client._sdk.annotations.delete = AsyncMock(side_effect=Exception("not found"))

        with pytest.raises(ExternalServiceException, match="LabelStudio delete_annotation"):
            await ls_client.delete_annotation(99)


class TestGetAnnotationResultTemplate:
    def test_image_classification(self):
        template = get_annotation_result_template("image_classification")
        assert template["from_name"] == "choice"
        assert template["to_name"] == "image"
        assert template["type"] == "choices"

    def test_text_classification(self):
        template = get_annotation_result_template("text_classification")
        assert template["from_name"] == "sentiment"
        assert template["to_name"] == "text"

    def test_object_detection(self):
        template = get_annotation_result_template("object_detection")
        assert template["type"] == "rectanglelabels"
        assert "x" in template["value_keys"]

    def test_image_segmentation(self):
        template = get_annotation_result_template("image_segmentation")
        assert template["type"] == "polygonlabels"

    def test_unknown_type(self):
        template = get_annotation_result_template("unknown")
        assert template == {}
