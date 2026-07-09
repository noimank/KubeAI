"""Tests for algorithm browser-register (file_paths) pipeline.

覆盖:
- ``AlgorithmRegisterRequest`` schema: file_paths 至少 1 个, name 非空, 长度限制.
- ``_pack_paths_to_zip``: 把单文件 / 多文件 / 目录子树打包成 zip, 保留相对层级.
- 跨用户身份首段 (``/kubeai/home/bob/...``) 在 service 入口被拒 — 由 ``FilesystemBrowserSecurity`` 已有单测覆盖, 此处只确保 service 抛 ``AppException``.

端点的鉴权 / 越权 / 文件不存在 / 名称冲突 (uq_algorithms_tenant_name) 由
``tests/integration`` 端到端跑覆盖 (本仓库的集成测试默认在共享测试 DB 上跑).
"""

from __future__ import annotations

import uuid
import zipfile
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from app.schemas.algorithm import AlgorithmRegisterRequest
from app.services.algorithm_service import _pack_paths_to_zip

if TYPE_CHECKING:
    from pathlib import Path


class TestAlgorithmRegisterRequest:
    def test_minimum_valid_payload(self) -> None:
        req = AlgorithmRegisterRequest(name="algo-1", file_paths=["/kubeai/home/alice/x.py"])
        assert req.name == "algo-1"
        assert req.tags == []
        assert req.description is None

    def test_empty_file_paths_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlgorithmRegisterRequest(name="algo-1", file_paths=[])

    def test_missing_file_paths_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlgorithmRegisterRequest(name="algo-1")  # type: ignore[call-arg]

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlgorithmRegisterRequest(name="", file_paths=["/kubeai/home/alice/x.py"])

    def test_name_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlgorithmRegisterRequest(name="a" * 201, file_paths=["/kubeai/home/alice/x.py"])


class TestPackPathsToZip:
    def test_single_file_uses_arcname(self, tmp_path: Path) -> None:
        src = tmp_path / "src.txt"
        src.write_text("hello", encoding="utf-8")
        algo_id = uuid.uuid4()

        zip_path = _pack_paths_to_zip([(src, "src.txt")], algo_id)

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert names == ["src.txt"]
            assert zf.read("src.txt").decode() == "hello"

    def test_directory_preserves_layout(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "exp-1"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print(1)", encoding="utf-8")
        sub = src_dir / "lib"
        sub.mkdir()
        (sub / "util.py").write_text("x=1", encoding="utf-8")
        algo_id = uuid.uuid4()

        zip_path = _pack_paths_to_zip([(src_dir, "exp-1")], algo_id)

        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            assert names == {"exp-1/main.py", "exp-1/lib/util.py"}
            assert zf.read("exp-1/main.py").decode() == "print(1)"
            assert zf.read("exp-1/lib/util.py").decode() == "x=1"

    def test_multiple_sources_dedup_arcnames(self, tmp_path: Path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("A", encoding="utf-8")
        b.write_text("B", encoding="utf-8")
        algo_id = uuid.uuid4()

        zip_path = _pack_paths_to_zip([(a, "a.txt"), (b, "b.txt")], algo_id)

        with zipfile.ZipFile(zip_path) as zf:
            assert set(zf.namelist()) == {"a.txt", "b.txt"}
            assert zf.read("a.txt").decode() == "A"
            assert zf.read("b.txt").decode() == "B"

    def test_empty_sources_writes_empty_zip(self, tmp_path: Path) -> None:
        algo_id = uuid.uuid4()
        zip_path = _pack_paths_to_zip([], algo_id)
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.namelist() == []
