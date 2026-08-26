"""上传/下载链路的文件名与路径安全工具 — 全仓统一防路径穿越。

- ``sanitize_filename``: 在入口归一化上传文件名, 保证只是一个普通文件名;
- ``resolve_within``: 在落盘/读取点校验路径未逃逸目标目录 (``../``、绝对路径、symlink);
- ``read_upload_bytes``: 分块读取上传内容并强制大小上限, 防整读内存 DoS。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import UploadFile

_FILENAME_MAX_LEN = 255
_CHUNK_SIZE = 1024 * 1024  # 1MB


def sanitize_filename(filename: str | None) -> str:
    """归一化上传文件名: 取最后一段 (兼容 Windows 反斜杠), 拒绝空名/穿越/控制字符.

    multipart 的 ``file.filename`` 可能是 ``../../evil``、绝对路径或含反斜杠;
    归一化后保证只是目标目录下的一个普通文件名, 从源头消除写穿越。
    """
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."} or len(name) > _FILENAME_MAX_LEN:
        raise ValueError(f"非法文件名: {filename!r}")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError(f"非法文件名: {filename!r}")
    return name


def resolve_within(base: Path, candidate: str) -> Path:
    """解析 ``candidate`` 相对 ``base`` 的绝对路径, 校验未逃逸 (防穿越/绝对路径/symlink).

    ``candidate`` 允许含子目录 (如 ``sub/model.bin``), 但解析后必须等于或在 base 内。
    """
    resolved_base = base.resolve()
    target = (resolved_base / candidate).resolve()
    if target != resolved_base and resolved_base not in target.parents:
        raise ValueError(f"非法路径: {candidate}")
    return target


async def read_upload_bytes(file: UploadFile) -> bytes:
    """分块读取上传内容, 超过 ``UPLOAD_MAX_FILE_BYTES`` 即抛错 (防整读内存 DoS)."""
    from app.core.config import settings

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.UPLOAD_MAX_FILE_BYTES:
            raise ValueError(f"文件超过大小上限 {settings.UPLOAD_MAX_FILE_BYTES} 字节")
        chunks.append(chunk)
    return b"".join(chunks)
