"""Tests for algorithm model."""

import uuid
from datetime import UTC, datetime

from app.models.algorithm import Algorithm

_NOW = datetime(2026, 6, 2, 12, 0, 0, tzinfo=UTC)
_TENANT_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


class TestAlgorithmModel:
    def test_create_algorithm_defaults(self):
        algo = Algorithm(
            name="test-algorithm",
            tenant_id=_TENANT_ID,
            user_id=_USER_ID,
        )
        assert algo.id is not None
        assert algo.name == "test-algorithm"
        assert algo.source_type == "upload"
        assert algo.status == "available"
        assert algo.visibility == "tenant"
        assert algo.tags == []
        assert algo.description is None
        assert algo.storage_path is None
        assert algo.size_bytes is None

    def test_create_algorithm_with_all_fields(self):
        algo = Algorithm(
            name="full-algo",
            description="A test algorithm",
            tags=["ml", "test"],
            source_type="upload",
            storage_path="test-tenant/algorithms/user-uuid/algo-uuid/algorithm.zip",
            size_bytes=1048576,
            status="available",
            visibility="tenant",
            tenant_id=_TENANT_ID,
            user_id=_USER_ID,
        )
        assert algo.name == "full-algo"
        assert algo.description == "A test algorithm"
        assert algo.tags == ["ml", "test"]
        assert algo.source_type == "upload"
        assert algo.storage_path == "test-tenant/algorithms/user-uuid/algo-uuid/algorithm.zip"
        assert algo.size_bytes == 1048576

    def test_algorithm_id_auto_generated(self):
        algo = Algorithm(name="test", tenant_id=_TENANT_ID, user_id=_USER_ID)
        assert isinstance(algo.id, uuid.UUID)

    def test_algorithm_id_explicit(self):
        custom_id = uuid.uuid4()
        algo = Algorithm(id=custom_id, name="test", tenant_id=_TENANT_ID, user_id=_USER_ID)
        assert algo.id == custom_id
