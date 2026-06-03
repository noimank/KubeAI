"""File-system-backed algorithm file storage service.

Handles storage and deletion of algorithm zip archives within the
tenant-scoped file-system path hierarchy, following the same pattern
as dataset storage.
"""

import shutil
import uuid
from pathlib import Path

from app.core.config import settings
from app.integrations.base import sanitize_k8s_name


class AlgorithmStorageService:
    """Service for algorithm file operations on the local file system."""

    def __init__(self, tenant_name: str, base_path: str | None = None) -> None:
        self._base_path = Path(base_path or settings.ALGORITHM_BASE_PATH)
        self._tenant_name = sanitize_k8s_name(tenant_name)

    def _algorithm_dir(self, user_id: uuid.UUID, algorithm_id: uuid.UUID) -> Path:
        """Build the algorithm directory path."""
        return self._base_path / self._tenant_name / str(user_id) / str(algorithm_id)

    def _zip_path(self, user_id: uuid.UUID, algorithm_id: uuid.UUID) -> Path:
        """Build the path for the algorithm zip file."""
        return self._algorithm_dir(user_id, algorithm_id) / "algorithm.zip"

    async def upload_algorithm_zip(
        self,
        user_id: uuid.UUID,
        algorithm_id: uuid.UUID,
        file_path: str,
    ) -> str:
        """Copy the algorithm zip file into the storage directory.

        Args:
            user_id: The uploading user's ID.
            algorithm_id: The algorithm record ID.
            file_path: Local path to the zip file to store.

        Returns:
            The relative storage path for the algorithm zip.

        Raises:
            OSError: If directory creation or file copy fails.
        """
        import asyncio

        dest_dir = self._algorithm_dir(user_id, algorithm_id)
        dest_path = self._zip_path(user_id, algorithm_id)

        def _copy() -> None:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, str(dest_path))

        await asyncio.to_thread(_copy)
        return str(dest_path.relative_to(self._base_path))

    def get_file_path(
        self,
        user_id: uuid.UUID,
        algorithm_id: uuid.UUID,
    ) -> Path:
        """Return the absolute path to the algorithm zip file.

        Returns the path even if the file does not yet exist.
        """
        return self._zip_path(user_id, algorithm_id)

    async def delete_algorithm_files(
        self,
        user_id: uuid.UUID,
        algorithm_id: uuid.UUID,
    ) -> None:
        """Delete all files for an algorithm (idempotent).

        Args:
            user_id: The owning user's ID.
            algorithm_id: The algorithm record ID.
        """
        import asyncio

        algo_dir = self._algorithm_dir(user_id, algorithm_id)

        def _remove() -> None:
            if algo_dir.exists():
                shutil.rmtree(str(algo_dir), ignore_errors=True)

        await asyncio.to_thread(_remove)
