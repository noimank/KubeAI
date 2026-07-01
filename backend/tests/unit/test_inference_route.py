"""推理服务 APISIX 路由模块的纯函数 / 行为测试.

覆盖 _build_apisix_route_payload (统一 Deployment + Service 上游, 不再有 traffic-split)、
地址生成、就绪判断, 以及 put_inference_route 的跳过 / 推送 / 吞异常行为.
"""

from __future__ import annotations

import uuid

import pytest

from app.integrations.k8s import inference_route
from app.integrations.k8s.inference_route import (
    _build_apisix_route_payload,
    _is_route_ready,
    delete_inference_route,
    inference_access_url,
    inference_path,
    put_inference_route,
)
from app.models.inference_service import InferenceService

_NAMESPACE = "kubeai-test"


def _make_svc(**kwargs: object) -> InferenceService:
    base: dict[str, object] = {"tenant_id": uuid.uuid4(), "created_by": uuid.uuid4(), "name": "test-svc"}
    base.update(kwargs)
    return InferenceService(**base)


# ── 地址 / 路径 / 就绪 ────────────────────────────────────────────────────────


def test_inference_path_uses_hex_id() -> None:
    sid = uuid.UUID("12345678-1234-1234-1234-1234567890ab")
    assert inference_path(sid) == "/inference/123456781234123412341234567890ab"


def test_inference_access_url_with_and_without_suffix() -> None:
    sid = uuid.uuid4()
    base = inference_access_url(sid)
    assert base.endswith(f"/inference/{sid.hex}")

    full = inference_access_url(sid, "v1/models/iris:predict")
    assert full == f"{base}/v1/models/iris:predict"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"k8s_service_name": "m1", "container_port": 8000}, True),
        ({"k8s_service_name": "m1"}, False),  # 缺 container_port
        ({}, False),  # 缺 service 名
    ],
)
def test_is_route_ready(kwargs: dict[str, object], expected: bool) -> None:
    assert _is_route_ready(_make_svc(**kwargs)) is expected


# ── payload 构建 ──────────────────────────────────────────────────────────────


def test_payload_targets_service_clusterip_has_auth_and_rewrite() -> None:
    svc = _make_svc(k8s_service_name="m1", container_port=8000, status="running")
    payload = _build_apisix_route_payload(svc=svc, namespace=_NAMESPACE)

    hex_id = svc.id.hex
    assert payload["id"] == hex_id
    # 同时匹配裸路径与带子路径 —— 无尾斜杠的访问也能命中, 不会落到平台 SPA 兜底路由.
    assert payload["uris"] == [f"/inference/{hex_id}", f"/inference/{hex_id}/*"]
    assert payload["enable_websocket"] is True
    assert payload["priority"] == 100

    # forward-auth 回 auth-check (双通道: Cookie 浏览器 + Authorization 程序化),
    # 透传 X-KubeAI-User 给上游.
    fa = payload["plugins"]["forward-auth"]
    assert fa["request_headers"] == ["Cookie", "Authorization"]
    assert fa["upstream_headers"] == ["X-KubeAI-User"]
    assert f"/api/inference-services/auth-check?service_id={svc.id}" in fa["uri"]

    # proxy-rewrite 剥 /inference/<hex> 前缀, /?(.*) 覆盖裸路径与带子路径.
    assert payload["plugins"]["proxy-rewrite"]["regex_uri"] == [
        f"^/inference/{hex_id}/?(.*)",
        "/$1",
    ]

    # upstream 直连推理 Service 的集群内 ClusterIP (model/custom 统一).
    assert payload["upstream"]["nodes"] == {f"m1.{_NAMESPACE}.svc.cluster.local:8000": 1}

    # 金丝雀已移除 — 永不出现 traffic-split.
    assert "traffic-split" not in payload["plugins"]


def test_payload_native_mode_omits_proxy_rewrite() -> None:
    # native 模式: 应用自行处理 /inference/<hex> 前缀, 平台不剥 —— 否则双重剥离致 404.
    svc = _make_svc(k8s_service_name="m1", container_port=8000, status="running", subpath_mode="native")
    payload = _build_apisix_route_payload(svc=svc, namespace=_NAMESPACE)

    hex_id = svc.id.hex
    assert "proxy-rewrite" not in payload["plugins"]
    # 其余契约不变: forward-auth 鉴权仍在, uris 仍同时匹配裸路径与子路径, upstream 直连不变.
    assert "forward-auth" in payload["plugins"]
    assert payload["uris"] == [f"/inference/{hex_id}", f"/inference/{hex_id}/*"]
    assert payload["upstream"]["nodes"] == {f"m1.{_NAMESPACE}.svc.cluster.local:8000": 1}


# ── put / delete 行为 ─────────────────────────────────────────────────────────


async def test_put_inference_route_skips_when_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[tuple[str, dict]] = []

    async def fake_put(route_id: str, payload: dict) -> None:
        pushed.append((route_id, payload))

    monkeypatch.setattr(inference_route, "put_route", fake_put)
    svc = _make_svc()  # 缺 k8s_service_name → 未就绪
    await put_inference_route(svc, _NAMESPACE)
    assert pushed == []


async def test_put_inference_route_pushes_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[tuple[str, dict]] = []

    async def fake_put(route_id: str, payload: dict) -> None:
        pushed.append((route_id, payload))

    monkeypatch.setattr(inference_route, "put_route", fake_put)
    svc = _make_svc(k8s_service_name="m1", container_port=8000, status="running")
    await put_inference_route(svc, _NAMESPACE)
    assert len(pushed) == 1
    assert pushed[0][0] == svc.id.hex


async def test_put_inference_route_swallows_admin_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_put(route_id: str, payload: dict) -> None:
        raise RuntimeError("apisix admin api down")

    monkeypatch.setattr(inference_route, "put_route", fake_put)
    svc = _make_svc(k8s_service_name="m1", container_port=8000, status="running")
    # 不应抛出 — 推送失败只 warn, 不阻塞部署流程.
    await put_inference_route(svc, _NAMESPACE)


async def test_delete_inference_route_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_delete(route_id: str) -> None:
        raise RuntimeError("apisix admin api down")

    monkeypatch.setattr(inference_route, "delete_route", fake_delete)
    # 不应抛出 — 删除是 best-effort.
    await delete_inference_route(uuid.uuid4())
