from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.exceptions import ExternalServiceException
from app.integrations.base import sanitize_k8s_name

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


class MinIOClient:
    def __init__(self) -> None:
        self._client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._prefix = settings.MINIO_BUCKET_PREFIX

    def close(self) -> None:
        http_pool = getattr(self._client, "_http", None)
        if http_pool is not None:
            http_pool.clear()

    def _bucket_name(self, tenant_name: str) -> str:
        return f"{self._prefix}{sanitize_k8s_name(tenant_name)}"

    async def _run_sync(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(partial(fn, *args, **kwargs))

    async def health_check(self) -> bool:
        try:
            await self._run_sync(self._client.list_buckets)
            return True
        except Exception as e:
            logger.error("MinIO health check failed: %s", e)
            raise ExternalServiceException(f"MinIO 连接失败: {e}") from e

    async def ensure_bucket(self, tenant_name: str) -> str:
        bucket = self._bucket_name(tenant_name)
        try:
            if not await self._run_sync(self._client.bucket_exists, bucket):
                await self._run_sync(self._client.make_bucket, bucket)
                logger.info("Created MinIO bucket: %s", bucket)
            return bucket
        except S3Error as e:
            raise ExternalServiceException(f"MinIO bucket 操作失败: {e}") from e

    async def upload_file(
        self,
        tenant_name: str,
        object_name: str,
        file_path: str,
        content_type: str = "application/octet-stream",
        part_size: int = 10 * 1024 * 1024,
    ) -> str:
        bucket = self._bucket_name(tenant_name)
        try:
            result = await self._run_sync(
                self._client.fput_object,
                bucket_name=bucket,
                object_name=object_name,
                file_path=file_path,
                content_type=content_type,
                part_size=part_size,
            )
            return result.object_name
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 文件上传失败: {e}") from e

    async def upload_stream(
        self,
        tenant_name: str,
        object_name: str,
        data: Any,
        length: int,
        content_type: str = "application/octet-stream",
        part_size: int = 10 * 1024 * 1024,
    ) -> str:
        bucket = self._bucket_name(tenant_name)
        try:
            result = await self._run_sync(
                self._client.put_object,
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

    async def list_objects(self, tenant_name: str, prefix: str = "") -> list[dict[str, Any]]:
        bucket = self._bucket_name(tenant_name)
        try:
            objects = await self._run_sync(self._client.list_objects, bucket, prefix=prefix, recursive=True)
            result: list[dict[str, Any]] = []
            for obj in objects:
                if obj.is_dir:
                    continue
                try:
                    result.append(
                        {
                            "object_name": obj.object_name or "",
                            "size": obj.size if obj.size is not None else 0,
                            "content_type": obj.content_type or "application/octet-stream",
                            "last_modified": obj.last_modified,
                        }
                    )
                except Exception as exc:
                    name = getattr(obj, "object_name", "<unknown>")
                    logger.warning("跳过无法读取的 MinIO 对象 %s: %s", name, exc)
            return result
        except S3Error as e:
            if e.code == "NoSuchBucket":
                return []
            raise ExternalServiceException(f"MinIO 列出对象失败: {e}") from e
        except Exception as e:
            raise ExternalServiceException(f"MinIO 列出对象失败: {e}") from e

    async def get_object_info(self, tenant_name: str, object_name: str) -> dict[str, Any]:
        bucket = self._bucket_name(tenant_name)
        try:
            stat = await self._run_sync(self._client.stat_object, bucket, object_name)
            return {
                "object_name": stat.object_name,
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
            }
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 获取对象信息失败: {e}") from e

    async def presigned_get_url(
        self,
        tenant_name: str,
        object_name: str,
        expires: timedelta = timedelta(hours=2),
        download_filename: str | None = None,
    ) -> str:
        bucket = self._bucket_name(tenant_name)
        try:
            extra_query: dict[str, str | list[str] | tuple[str]] = {}
            if download_filename:
                extra_query["response-content-disposition"] = f'attachment; filename="{download_filename}"'
            return await self._run_sync(
                self._client.presigned_get_object, bucket, object_name, expires=expires, extra_query_params=extra_query
            )
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 生成预签名 URL 失败: {e}") from e

    async def delete_object(self, tenant_name: str, object_name: str) -> None:
        bucket = self._bucket_name(tenant_name)
        try:
            await self._run_sync(self._client.remove_object, bucket, object_name)
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 删除对象失败: {e}") from e

    async def delete_objects(self, tenant_name: str, object_names: list[str]) -> None:
        bucket = self._bucket_name(tenant_name)
        try:
            for name in object_names:
                await self._run_sync(self._client.remove_object, bucket, name)
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 批量删除失败: {e}") from e

    async def copy_object(self, src_tenant: str, src_object: str, dst_tenant: str, dst_object: str) -> None:
        from minio.commonconfig import CopySource

        src_bucket = self._bucket_name(src_tenant)
        dst_bucket = self._bucket_name(dst_tenant)
        try:
            await self._run_sync(
                self._client.copy_object,
                dst_bucket,
                dst_object,
                CopySource(src_bucket, src_object),
            )
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 对象复制失败: {e}") from e

    async def get_object_content(self, tenant_name: str, object_name: str) -> bytes:
        bucket = self._bucket_name(tenant_name)
        try:
            response = await self._run_sync(self._client.get_object, bucket, object_name)
            try:
                content: bytes = response.read()
                return content
            finally:
                response.close()
                response.release_conn()
        except S3Error as e:
            raise ExternalServiceException(f"MinIO 读取对象失败: {e}") from e
