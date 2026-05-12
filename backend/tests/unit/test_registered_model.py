import uuid

from app.models.registered_model import ModelVersion, RegisteredModel


def test_registered_model_creation():
    model = RegisteredModel(
        tenant_id=uuid.uuid4(),
        name="test-model",
        created_by=uuid.uuid4(),
    )
    assert model.id is not None
    assert model.name == "test-model"


def test_model_version_creation():
    model_id = uuid.uuid4()
    version = ModelVersion(
        registered_model_id=model_id,
        version_number=1,
        storage_path="models/test-model/v1",
        file_count=2,
        total_size_bytes=1024,
        created_by=uuid.uuid4(),
    )
    assert version.id is not None
    assert version.registered_model_id == model_id
    assert version.version_number == 1


def test_model_version_with_training_job():
    version = ModelVersion(
        registered_model_id=uuid.uuid4(),
        version_number=1,
        storage_path="models/test/v1",
        file_count=1,
        total_size_bytes=512,
        training_job_id=uuid.uuid4(),
        hyperparameters={"lr": "0.001"},
        created_by=uuid.uuid4(),
    )
    assert version.training_job_id is not None
    assert version.hyperparameters == {"lr": "0.001"}


def test_model_unique_constraint():
    """Verify the unique constraint is properly set."""
    assert RegisteredModel.__table_args__ is not None
    constraint = RegisteredModel.__table_args__[0]
    assert constraint.name == "uq_model_tenant_name"
    assert set(constraint.columns.keys()) == {"tenant_id", "name"}
