import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from app.api.endpoints.model_registry import (
    _build_model_response,
    _build_version_response,
    _next_version_number,
    _resolve_dataset_info,
    _resolve_image_info,
    _resolve_training_job_names,
)
from app.models.registered_model import ModelVersion, RegisteredModel

_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)


def _make_model(**overrides):
    defaults = {
        "tenant_id": uuid.uuid4(),
        "name": "test-model",
        "created_by": uuid.uuid4(),
    }
    defaults.update(overrides)
    model = RegisteredModel(**defaults)
    model.created_at = _NOW
    model.updated_at = _NOW
    return model


def _make_version(**overrides):
    defaults = {
        "registered_model_id": uuid.uuid4(),
        "version_number": 1,
        "storage_path": "models/test/v1",
        "status": "available",
        "file_count": 2,
        "total_size_bytes": 1024,
        "created_by": uuid.uuid4(),
    }
    defaults.update(overrides)
    version = ModelVersion(**defaults)
    version.created_at = _NOW
    version.updated_at = _NOW
    return version


class TestBuildModelResponse:
    def test_basic_fields(self):
        model = _make_model()
        resp = _build_model_response(model)
        assert resp.id == model.id
        assert resp.name == "test-model"
        assert resp.version_count == 0
        assert resp.latest_version is None

    def test_with_versions(self):
        model = _make_model()
        v1 = _make_version(registered_model_id=model.id, version_number=1)
        v2 = _make_version(registered_model_id=model.id, version_number=2)
        model.versions = [v1, v2]

        resp = _build_model_response(model)
        assert resp.version_count == 2
        assert resp.latest_version is not None
        assert resp.latest_version.version_number == 2

    def test_with_user_name_map(self):
        model = _make_model()
        resp = _build_model_response(model, {model.created_by: "alice"})
        assert resp.created_by_name == "alice"


class TestBuildVersionResponse:
    def test_basic_fields(self):
        version = _make_version(hyperparameters={"lr": "0.001"})
        resp = _build_version_response(version)
        assert resp.id == version.id
        assert resp.version_number == 1
        assert resp.storage_path == "models/test/v1"
        assert resp.hyperparameters == {"lr": "0.001"}

    def test_with_training_job(self):
        job_id = uuid.uuid4()
        version = _make_version(training_job_id=job_id)
        resp = _build_version_response(version, "my-training-job")
        assert resp.training_job_id == job_id
        assert resp.training_job_name == "my-training-job"

    def test_training_job_name_default_none(self):
        version = _make_version()
        resp = _build_version_response(version)
        assert resp.training_job_name is None


class TestNextVersionNumber:
    async def test_first_version(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        ver = await _next_version_number(db, uuid.uuid4())
        assert ver == 1

    async def test_increment(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = 3
        db.execute.return_value = result

        ver = await _next_version_number(db, uuid.uuid4())
        assert ver == 4


class TestBuildModelResponseWithTrainingJobName:
    def test_latest_version_includes_training_job_name(self):
        model = _make_model()
        job_id = uuid.uuid4()
        v1 = _make_version(registered_model_id=model.id, version_number=1, training_job_id=job_id)
        model.versions = [v1]

        resp = _build_model_response(model, training_job_names={job_id: "job-alpha"})
        assert resp.latest_version is not None
        assert resp.latest_version.training_job_name == "job-alpha"

    def test_no_training_job_name_when_not_provided(self):
        model = _make_model()
        v1 = _make_version(registered_model_id=model.id, version_number=1, training_job_id=uuid.uuid4())
        model.versions = [v1]

        resp = _build_model_response(model)
        assert resp.latest_version is not None
        assert resp.latest_version.training_job_name is None


class TestResolveTrainingJobNames:
    async def test_empty_versions(self):
        db = AsyncMock()
        result = await _resolve_training_job_names(db, [])
        assert result == {}

    async def test_no_training_job_ids(self):
        db = AsyncMock()
        version = _make_version(training_job_id=None)
        result = await _resolve_training_job_names(db, [version])
        assert result == {}

    async def test_resolves_names(self):
        db = AsyncMock()
        job_id = uuid.uuid4()
        version = _make_version(training_job_id=job_id)

        row = MagicMock()
        row.id = job_id
        row.name = "my-job"
        result_mock = MagicMock()
        result_mock.all.return_value = [row]
        db.execute.return_value = result_mock

        result = await _resolve_training_job_names(db, [version])
        assert result[job_id] == "my-job"


class TestBuildVersionResponseLineageFields:
    def test_dataset_fields(self):
        ds_id = uuid.uuid4()
        version = _make_version(dataset_id=ds_id)
        resp = _build_version_response(
            version,
            dataset_name="my-dataset",
            dataset_version_number=3,
        )
        assert resp.dataset_name == "my-dataset"
        assert resp.dataset_version_number == 3

    def test_image_fields(self):
        version = _make_version(image_id=uuid.uuid4())
        resp = _build_version_response(version, image_name="pytorch", image_tag="2.0-cuda12")
        assert resp.image_name == "pytorch"
        assert resp.image_tag == "2.0-cuda12"

    def test_lineage_fields_default_none(self):
        version = _make_version()
        resp = _build_version_response(version)
        assert resp.dataset_name is None
        assert resp.dataset_version_number is None
        assert resp.image_name is None
        assert resp.image_tag is None


class TestBuildModelResponseLineageFields:
    def test_latest_version_includes_dataset_info(self):
        model = _make_model()
        ds_id = uuid.uuid4()
        dsv_id = uuid.uuid4()
        v1 = _make_version(
            registered_model_id=model.id,
            version_number=1,
            dataset_id=ds_id,
            dataset_version_id=dsv_id,
        )
        model.versions = [v1]

        resp = _build_model_response(
            model,
            dataset_names={ds_id: "my-dataset"},
            dataset_version_numbers={dsv_id: 5},
        )
        assert resp.latest_version is not None
        assert resp.latest_version.dataset_name == "my-dataset"
        assert resp.latest_version.dataset_version_number == 5

    def test_latest_version_includes_image_info(self):
        model = _make_model()
        img_id = uuid.uuid4()
        v1 = _make_version(
            registered_model_id=model.id,
            version_number=1,
            image_id=img_id,
        )
        model.versions = [v1]

        resp = _build_model_response(
            model,
            image_info={img_id: ("tensorflow", "2.15-gpu")},
        )
        assert resp.latest_version is not None
        assert resp.latest_version.image_name == "tensorflow"
        assert resp.latest_version.image_tag == "2.15-gpu"

    def test_no_lineage_info_when_not_provided(self):
        model = _make_model()
        v1 = _make_version(
            registered_model_id=model.id,
            version_number=1,
            dataset_id=uuid.uuid4(),
            image_id=uuid.uuid4(),
        )
        model.versions = [v1]

        resp = _build_model_response(model)
        assert resp.latest_version is not None
        assert resp.latest_version.dataset_name is None
        assert resp.latest_version.image_name is None


class TestResolveDatasetInfo:
    async def test_empty_versions(self):
        db = AsyncMock()
        names, nums = await _resolve_dataset_info(db, [])
        assert names == {}
        assert nums == {}

    async def test_no_dataset_ids(self):
        db = AsyncMock()
        version = _make_version(dataset_id=None, dataset_version_id=None)
        names, nums = await _resolve_dataset_info(db, [version])
        assert names == {}
        assert nums == {}

    async def test_resolves_dataset_info(self):
        db = AsyncMock()
        ds_id = uuid.uuid4()
        dsv_id = uuid.uuid4()
        version = _make_version(dataset_id=ds_id, dataset_version_id=dsv_id)

        ds_row = MagicMock()
        ds_row.id = ds_id
        ds_row.name = "cifar-10"
        ds_result = MagicMock()
        ds_result.all.return_value = [ds_row]

        dsv_row = MagicMock()
        dsv_row.id = dsv_id
        dsv_row.version_number = 2
        dsv_result = MagicMock()
        dsv_result.all.return_value = [dsv_row]

        db.execute.side_effect = [ds_result, dsv_result]

        names, nums = await _resolve_dataset_info(db, [version])
        assert names[ds_id] == "cifar-10"
        assert nums[dsv_id] == 2


class TestResolveImageInfo:
    async def test_empty_versions(self):
        db = AsyncMock()
        result = await _resolve_image_info(db, [])
        assert result == {}

    async def test_no_image_ids(self):
        db = AsyncMock()
        version = _make_version(image_id=None)
        result = await _resolve_image_info(db, [version])
        assert result == {}

    async def test_resolves_image_info(self):
        db = AsyncMock()
        img_id = uuid.uuid4()
        version = _make_version(image_id=img_id)

        row = MagicMock()
        row.id = img_id
        row.name = "pytorch"
        row.tag = "2.0-cuda12"
        result_mock = MagicMock()
        result_mock.all.return_value = [row]
        db.execute.return_value = result_mock

        result = await _resolve_image_info(db, [version])
        assert result[img_id] == ("pytorch", "2.0-cuda12")
