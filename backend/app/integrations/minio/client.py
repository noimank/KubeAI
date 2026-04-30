from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.exceptions import ExternalServiceException
from app.integrations.base import BaseIntegration, with_retry

if TYPE_CHECKING:
    import uuid

logger = logging.getLogger(__name__)


class MinIOClient(BaseIntegration):
    def __init__(self) -> None:
        self._client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._prefix = settings.MINIO_BUCKET_PREFIX

    def _bucket_name(self, tenant_id: uuid.UUID | str) -> str:
        return f"{self._prefix}{tenant_id}"

    @with_retry()
    def health_check(self) -> bool:
        try:
            self._client.list_buckets()
            return True
        except Exception as e:
            logger.error("MinIO health check failed: %s", e)
            raise ExternalServiceException(f"MinIO 连接失败: {e}") from e

    @with_retry()
    def ensure_bucket(self, tenant_id: uuid.UUID | str) -> str:
        bucket = self._bucket_name(tenant_id)
        try:
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)
                logger.info("Created MinIO bucket: %s", bucket)
            return bucket
        except S3Error as e:
            raise ExternalServiceException(f"MinIO bucket 操作失败: {e}") from e

    @with_retry()
    def upload_file(
        self,
        tenant_id: uuid.UUID | str,
        object_name: str,
        file_path: str,
        content_type: str = "application/octet-stream",
        part_size: int = 10 * 1024 * 1024,
    ) -> str:
        bucket = self._bucket_name(tenant_id)
        try:
            result = self._client.fput_object(
                bucket_name=bucket,
                object_name=object_name,
                file_path=file_path,
                content_type=content_type,
                part_size=part_size,
            )
            return result.object_name
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 文件上传失败: {e}") from e

    @with_retry()
    def upload_stream(
        self,
        tenant_id: uuid.UUID | str,
        object_name: str,
        data: Any,
        length: int,
        content_type: str = "application/octet-stream",
        part_size: int = 10 * 1024 * 1024,
    ) -> str:
        bucket = self._bucket_name(tenant_id)
        try:
            result = self._client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type,
                part_size=part_size,
            )
            return result.object_name
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 流式上传失败: {e}") from e

    @with_retry()
    def list_objects(self, tenant_id: uuid.UUID | str, prefix: str = "") -> list[dict[str, Any]]:
        bucket = self._bucket_name(tenant_id)
        try:
            objects = self._client.list_objects(bucket, prefix=prefix, recursive=True)
            return [
                {
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "content_type": obj.content_type,
                    "last_modified": obj.last_modified,
                }
                for obj in objects
                if not obj.is_dir
            ]
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 列出对象失败: {e}") from e

    @with_retry()
    def get_object_info(self, tenant_id: uuid.UUID | str, object_name: str) -> dict[str, Any]:
        bucket = self._bucket_name(tenant_id)
        try:
            stat = self._client.stat_object(bucket, object_name)
            return {
                "object_name": stat.object_name,
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
            }
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 获取对象信息失败: {e}") from e

    @with_retry()
    def presigned_get_url(
        self, tenant_id: uuid.UUID | str, object_name: str, expires: timedelta = timedelta(hours=2)
    ) -> str:
        bucket = self._bucket_name(tenant_id)
        try:
            return self._client.presigned_get_object(bucket, object_name, expires=expires)
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 生成预签名 URL 失败: {e}") from e

    @with_retry()
    def delete_object(self, tenant_id: uuid.UUID | str, object_name: str) -> None:
        bucket = self._bucket_name(tenant_id)
        try:
            self._client.remove_object(bucket, object_name)
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 删除对象失败: {e}") from e

    @with_retry()
    def delete_objects(self, tenant_id: uuid.UUID | str, object_names: list[str]) -> None:
        bucket = self._bucket_name(tenant_id)
        try:
            for name in object_names:
                self._client.remove_object(bucket, name)
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 批量删除失败: {e}") from e
