"""path_safety 单元测试 — 文件名归一化与 containment 校验.

覆盖维度:
  * sanitize_filename: 剥离目录段(含反斜杠) / 拒绝 ..、绝对路径残留、空名、控制字符、超长
  * resolve_within: 目录内放行 / ../ 逃逸拒绝 / 绝对路径拒绝 / symlink 逃逸拒绝
  * read_upload_bytes: 超过 UPLOAD_MAX_FILE_BYTES 拒绝
"""

import os
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.integrations.storage.path_safety import read_upload_bytes, resolve_within, sanitize_filename


class TestSanitizeFilename:
    def test_plain_name_unchanged(self):
        assert sanitize_filename("data.csv") == "data.csv"

    def test_strips_unix_directory_components(self):
        assert sanitize_filename("../../evil.sh") == "evil.sh"

    def test_strips_windows_backslash_components(self):
        assert sanitize_filename("..\\..\\evil.bat") == "evil.bat"

    def test_strips_absolute_path(self):
        assert sanitize_filename("/etc/passwd") == "passwd"

    @pytest.mark.parametrize("bad", ["..", ".", "", None, "a/..", "a/."])
    def test_rejects_traversal_only_names(self, bad):
        with pytest.raises(ValueError, match="非法文件名"):
            sanitize_filename(bad)

    def test_rejects_control_characters(self):
        with pytest.raises(ValueError, match="非法文件名"):
            sanitize_filename("evil\x00name")

    def test_rejects_overlong_name(self):
        with pytest.raises(ValueError, match="非法文件名"):
            sanitize_filename("a" * 256)


class TestResolveWithin:
    def test_file_inside_base_allowed(self, tmp_path):
        assert resolve_within(tmp_path, "a.csv") == (tmp_path / "a.csv").resolve()

    def test_subdirectory_allowed(self, tmp_path):
        target = resolve_within(tmp_path, "sub/model.bin")
        assert target == (tmp_path / "sub" / "model.bin").resolve()

    def test_parent_traversal_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="非法路径"):
            resolve_within(tmp_path, "../secret.txt")

    def test_absolute_path_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="非法路径"):
            resolve_within(tmp_path, "/etc/passwd")

    @pytest.mark.skipif(os.name == "nt", reason="Windows 创建符号链接需要特权")
    def test_symlink_escape_rejected(self, tmp_path):
        outside = tmp_path.parent / "outside-safe-dir"
        outside.mkdir(exist_ok=True)
        link = tmp_path / "escape"
        os.symlink(outside, link)
        try:
            with pytest.raises(ValueError, match="非法路径"):
                resolve_within(tmp_path, "escape/file.txt")
        finally:
            link.unlink()
            outside.rmdir()


class TestReadUploadBytes:
    async def test_reads_content(self):
        file = AsyncMock()
        file.read.side_effect = [b"hello ", b"world", b""]
        assert await read_upload_bytes(file) == b"hello world"

    async def test_rejects_oversized(self, monkeypatch):
        monkeypatch.setattr(settings, "UPLOAD_MAX_FILE_BYTES", 4)
        file = AsyncMock()
        file.read.side_effect = [b"12345", b""]
        with pytest.raises(ValueError, match="大小上限"):
            await read_upload_bytes(file)
