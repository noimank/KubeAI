import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from app.api.endpoints.model_registry import (
    _build_model_response,
    _build_version_response,
    _next_version_number,
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
        resp = _build_version_response(version)
        assert resp.training_job_id == job_id


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
