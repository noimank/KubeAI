"""模型版本部署配置 (deploy_config) — schema 校验 / 存取转换 / 推理创建回填."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.api.endpoints.model_registry import (
    _deploy_config_response,
    _dump_deploy_config,
    _resolve_image_info,
)
from app.core.exceptions import BadRequestException
from app.models.registered_model import ModelVersion
from app.schemas.inference_service import InferenceServiceCreateRequest
from app.schemas.model_registry import ModelDeployConfig
from app.services.inference_service import resolve_deploy_defaults

_NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)


def _make_version(**overrides) -> ModelVersion:
    defaults = {
        "registered_model_id": uuid.uuid4(),
        "version_number": 1,
        "storage_path": "models/test/v1",
        "status": "available",
        "file_count": 2,
        "total_size_bytes": 1024,
        "created_by": uuid.uuid4(),
    }
    defaults.update(overrides)
    version = ModelVersion(**defaults)
    version.created_at = _NOW
    version.updated_at = _NOW
    return version


class TestModelDeployConfigSchema:
    def test_defaults_empty(self):
        cfg = ModelDeployConfig()
        assert cfg.image_ids == []
        assert cfg.container_port is None
        assert cfg.subpath_mode is None
        assert cfg.gpu_count is None

    def test_full_config(self):
        image_id = uuid.uuid4()
        cfg = ModelDeployConfig(
            image_ids=[image_id],
            container_port=8000,
            subpath_mode="native",
            command=["vllm", "serve"],
            args=["--port", "8000"],
            env_vars={"A": "1"},
            gpu_count=1,
            cpu="4",
            memory="16Gi",
            replicas=2,
        )
        assert cfg.image_ids == [image_id]
        assert cfg.container_port == 8000
        assert cfg.replicas == 2

    def test_port_bounds(self):
        with pytest.raises(ValidationError):
            ModelDeployConfig(container_port=0)
        with pytest.raises(ValidationError):
            ModelDeployConfig(container_port=65536)

    def test_subpath_mode_enum(self):
        with pytest.raises(ValidationError):
            ModelDeployConfig(subpath_mode="nativee")

    def test_replicas_bounds(self):
        with pytest.raises(ValidationError):
            ModelDeployConfig(replicas=11)


class TestDumpDeployConfig:
    def test_none(self):
        assert _dump_deploy_config(None) is None

    def test_empty_config_dropped(self):
        assert _dump_deploy_config(ModelDeployConfig()) is None

    def test_full_config_json_serializable(self):
        image_id = uuid.uuid4()
        data = _dump_deploy_config(ModelDeployConfig(image_ids=[image_id], container_port=8000, subpath_mode="rewrite"))
        assert data == {
            "image_ids": [str(image_id)],
            "container_port": 8000,
            "subpath_mode": "rewrite",
        }


class TestDeployConfigResponse:
    def test_no_config(self):
        assert _deploy_config_response(_make_version()) is None

    def test_resolves_image_names(self):
        image_id = uuid.uuid4()
        version = _make_version(
            deploy_config={"image_ids": [str(image_id)], "container_port": 8000, "command": ["vllm", "serve"]}
        )
        resp = _deploy_config_response(version, {image_id: ("vllm", "0.7")})
        assert resp is not None
        assert len(resp.images) == 1
        assert resp.images[0].image_id == image_id
        assert resp.images[0].image_name == "vllm"
        assert resp.images[0].image_tag == "0.7"
        assert resp.container_port == 8000
        assert resp.command == ["vllm", "serve"]

    def test_image_name_unknown(self):
        image_id = uuid.uuid4()
        version = _make_version(deploy_config={"image_ids": [str(image_id)]})
        resp = _deploy_config_response(version)
        assert resp is not None
        assert resp.images[0].image_id == image_id
        assert resp.images[0].image_name is None


class TestResolveImageInfoIncludesDeployConfig:
    async def test_collects_deploy_image_ids(self):
        deploy_image_id = uuid.uuid4()
        version = _make_version(deploy_config={"image_ids": [str(deploy_image_id)]})

        db = AsyncMock()
        row = MagicMock()
        row.id = deploy_image_id
        row.name = "vllm"
        row.tag = "0.7"
        result_mock = MagicMock()
        result_mock.all.return_value = [row]
        db.execute.return_value = result_mock

        result = await _resolve_image_info(db, [version])
        assert result[deploy_image_id] == ("vllm", "0.7")


class TestInferenceCreateRequestRelaxed:
    def test_model_version_allows_missing_image_and_port(self):
        req = InferenceServiceCreateRequest(name="svc", model_version_id=uuid.uuid4())
        assert req.cpu is None
        assert req.subpath_mode is None

    def test_without_model_version_requires_image_and_port(self):
        with pytest.raises(ValidationError, match="推理运行时镜像"):
            InferenceServiceCreateRequest(name="svc", container_port=8000)
        with pytest.raises(ValidationError, match="容器端口"):
            InferenceServiceCreateRequest(name="svc", image="nginx:latest")

    def test_without_model_version_full_payload(self):
        req = InferenceServiceCreateRequest(name="svc", image="nginx:latest", container_port=8080)
        assert req.container_port == 8080


def _defaults_kwargs(**overrides):
    kwargs = dict(
        image=None,
        image_id=None,
        container_port=None,
        command=None,
        args=None,
        env_vars=None,
        subpath_mode=None,
        gpu_count=None,
        cpu=None,
        memory=None,
        replicas=None,
        deploy_config=None,
    )
    kwargs.update(overrides)
    return kwargs


class TestResolveDeployDefaults:
    def test_platform_defaults_when_nothing_given(self):
        r = resolve_deploy_defaults(**_defaults_kwargs(image="x:1", container_port=8080))
        assert r["gpu_count"] == 0
        assert r["cpu"] == "2"
        assert r["memory"] == "4Gi"
        assert r["replicas"] == 1
        assert r["subpath_mode"] == "rewrite"
        assert r["env_vars"] is None

    def test_config_fills_missing(self):
        deploy_image_id = uuid.uuid4()
        cfg = {
            "image_ids": [str(deploy_image_id)],
            "container_port": 8000,
            "command": ["vllm", "serve"],
            "args": ["--host", "0.0.0.0"],
            "env_vars": {"A": "1", "B": "cfg"},
            "subpath_mode": "native",
            "gpu_count": 2,
            "cpu": "8",
            "memory": "32Gi",
            "replicas": 3,
        }
        r = resolve_deploy_defaults(**_defaults_kwargs(deploy_config=cfg))
        assert r["image_id"] == deploy_image_id
        assert r["container_port"] == 8000
        assert r["command"] == ["vllm", "serve"]
        assert r["gpu_count"] == 2
        assert r["cpu"] == "8"
        assert r["memory"] == "32Gi"
        assert r["replicas"] == 3
        assert r["subpath_mode"] == "native"

    def test_user_values_win_over_config(self):
        cfg = {"image_ids": [str(uuid.uuid4())], "container_port": 8000, "cpu": "8", "env_vars": {"A": "cfg"}}
        r = resolve_deploy_defaults(
            **_defaults_kwargs(container_port=9000, cpu="4", env_vars={"A": "user"}, deploy_config=cfg)
        )
        assert r["container_port"] == 9000
        assert r["cpu"] == "4"
        assert r["env_vars"] == {"A": "user"}

    def test_env_vars_merge_user_overrides(self):
        cfg = {"image_ids": [str(uuid.uuid4())], "env_vars": {"A": "1", "B": "cfg"}, "container_port": 8000}
        r = resolve_deploy_defaults(**_defaults_kwargs(env_vars={"B": "user"}, deploy_config=cfg))
        assert r["env_vars"] == {"A": "1", "B": "user"}

    def test_first_image_id_is_default(self):
        first, second = uuid.uuid4(), uuid.uuid4()
        cfg = {"image_ids": [str(first), str(second)], "container_port": 8000}
        r = resolve_deploy_defaults(**_defaults_kwargs(deploy_config=cfg))
        assert r["image_id"] == first

    def test_missing_image_raises(self):
        with pytest.raises(BadRequestException, match="推理运行时镜像"):
            resolve_deploy_defaults(**_defaults_kwargs(container_port=8000))

    def test_missing_port_raises_even_with_config_image(self):
        cfg = {"image_ids": [str(uuid.uuid4())]}
        with pytest.raises(BadRequestException, match="容器端口"):
            resolve_deploy_defaults(**_defaults_kwargs(deploy_config=cfg))

    def test_explicit_image_string_bypasses_config(self):
        cfg = {"image_ids": [str(uuid.uuid4())], "container_port": 8000}
        r = resolve_deploy_defaults(**_defaults_kwargs(image="my-registry/app:1", deploy_config=cfg))
        assert r["image"] == "my-registry/app:1"
        assert r["image_id"] is None
