import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AlgorithmCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class AlgorithmRegisterRequest(BaseModel):
    """从文件浏览器勾选的文件/目录注册为算法.

    ``file_paths`` 是 canonical 容器内路径 (形如 ``/kubeai/home/<user>/<rel>`` 或
    ``/kubeai/workspace/<tenant>/<rel>``); 端点会复用
    :class:`FilesystemBrowserSecurity` 校验身份首段与防 ``..``/symlink 逃逸.
    """

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(..., min_length=1)


class AlgorithmUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] | None = None


class AlgorithmUploaderResponse(BaseModel):
    id: uuid.UUID
    username: str


class AlgorithmResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    tags: list[str]
    source_type: str
    size_bytes: int | None = None
    status: str
    visibility: str
    uploader: AlgorithmUploaderResponse | None = None
    created_at: datetime
    updated_at: datetime


class AlgorithmDetailResponse(AlgorithmResponse):
    storage_path: str | None = None
