"""Tests for AlgorithmStorageService (filesystem-backed algorithm file operations)."""

import os
import shutil
import tempfile
import uuid

import pytest

from app.services.algorithm_storage_service import AlgorithmStorageService


@pytest.fixture
def base_path():
    tmp = tempfile.mkdtemp(prefix="test-algorithms-")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def tenant_name():
    return "test-tenant"


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def algorithm_id():
    return uuid.uuid4()


@pytest.fixture
def service(tenant_name, base_path):
    return AlgorithmStorageService(tenant_name, base_path=base_path)


class TestUploadAlgorithmZip:
    async def test_upload_stores_file(self, service, base_path, user_id, algorithm_id):
        # Create a temporary source zip
        src_dir = tempfile.mkdtemp()
        src_zip = os.path.join(src_dir, "test.zip")
        with open(src_zip, "wb") as f:
            f.write(b"algorithm content")

        try:
            storage_path = await service.upload_algorithm_zip(user_id, algorithm_id, src_zip)

            # Verify the relative path is correct
            assert storage_path.endswith("algorithm.zip")
            assert str(user_id) in storage_path
            assert str(algorithm_id) in storage_path

            # Verify the file exists on disk
            file_path = service.get_file_path(user_id, algorithm_id)
            assert file_path.exists()
            assert file_path.read_bytes() == b"algorithm content"
        finally:
            shutil.rmtree(src_dir, ignore_errors=True)

    async def test_upload_creates_parent_directories(self, service, base_path, user_id, algorithm_id):
        src_dir = tempfile.mkdtemp()
        src_zip = os.path.join(src_dir, "test.zip")
        with open(src_zip, "wb") as f:
            f.write(b"data")

        try:
            await service.upload_algorithm_zip(user_id, algorithm_id, src_zip)

            algo_dir = service._algorithm_dir(user_id, algorithm_id)
            assert algo_dir.exists()
            assert algo_dir.is_dir()
        finally:
            shutil.rmtree(src_dir, ignore_errors=True)

    async def test_upload_overwrites_existing(self, service, base_path, user_id, algorithm_id):
        src_dir1 = tempfile.mkdtemp()
        src_zip1 = os.path.join(src_dir1, "v1.zip")
        with open(src_zip1, "wb") as f:
            f.write(b"version 1")

        src_dir2 = tempfile.mkdtemp()
        src_zip2 = os.path.join(src_dir2, "v2.zip")
        with open(src_zip2, "wb") as f:
            f.write(b"version 2 updated")

        try:
            await service.upload_algorithm_zip(user_id, algorithm_id, src_zip1)
            await service.upload_algorithm_zip(user_id, algorithm_id, src_zip2)

            file_path = service.get_file_path(user_id, algorithm_id)
            assert file_path.read_bytes() == b"version 2 updated"
        finally:
            shutil.rmtree(src_dir1, ignore_errors=True)
            shutil.rmtree(src_dir2, ignore_errors=True)


class TestGetFile:
    def test_get_file_path_returns_absolute_path(self, service, base_path, user_id, algorithm_id):
        file_path = service.get_file_path(user_id, algorithm_id)

        assert file_path.is_absolute()
        assert file_path.name == "algorithm.zip"
        assert str(user_id) in str(file_path)
        assert str(algorithm_id) in str(file_path)


class TestDeleteAlgorithmFiles:
    async def test_delete_removes_directory(self, service, base_path, user_id, algorithm_id):
        # First upload something
        src_dir = tempfile.mkdtemp()
        src_zip = os.path.join(src_dir, "test.zip")
        with open(src_zip, "wb") as f:
            f.write(b"data")

        try:
            await service.upload_algorithm_zip(user_id, algorithm_id, src_zip)

            algo_dir = service._algorithm_dir(user_id, algorithm_id)
            assert algo_dir.exists()

            await service.delete_algorithm_files(user_id, algorithm_id)
            assert not algo_dir.exists()
        finally:
            shutil.rmtree(src_dir, ignore_errors=True)

    async def test_delete_idempotent(self, service, user_id, algorithm_id):
        # Should not raise when deleting non-existent files
        await service.delete_algorithm_files(user_id, algorithm_id)
        # No exception = success
