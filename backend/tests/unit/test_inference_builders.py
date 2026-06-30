"""推理运行时构建器单测 — Deployment + 共享卷 + chown initContainer + KEDA 触发器.

推理服务统一为裸 Deployment + Service + KEDA ScaledObject, Pod 挂 KubeAI 共享卷
(home/workspace) 并用 busybox initContainer chown 归属. 本测试覆盖这些纯函数构建器.
"""

from __future__ import annotations

from app.core.config import settings
from app.integrations.k8s.deployment import build_deployment, build_resource_spec
from app.integrations.k8s.kubeai_volumes import (
    build_chown_init_container,
    build_kubeai_env_vars,
    build_kubeai_volumes,
)
from app.integrations.k8s.pvc import make_user_home_host_path, make_workspace_host_path
from app.integrations.keda.builder import build_scaled_object

_NAMESPACE = "kubeai-test"


# ── build_resource_spec ─────────────────────────────────────────────────────


def test_build_resource_spec_without_gpu() -> None:
    spec = build_resource_spec("2", "4Gi", 0)
    assert spec == {
        "requests": {"cpu": "2", "memory": "4Gi"},
        "limits": {"cpu": "2", "memory": "4Gi"},
    }


def test_build_resource_spec_with_gpu() -> None:
    spec = build_resource_spec("8", "16Gi", 2)
    assert spec["requests"]["nvidia.com/gpu"] == "2"
    assert spec["limits"]["nvidia.com/gpu"] == "2"


# ── build_kubeai_volumes (home + workspace hostPath, 与开发环境同源) ──────────


def test_build_kubeai_volumes_wires_home_and_workspace_hostpath() -> None:
    volumes, mounts = build_kubeai_volumes(username="alice", tenant_name="acme")

    assert volumes == [
        {"name": "home-volume", "hostPath": {"path": make_user_home_host_path("alice"), "type": "DirectoryOrCreate"}},
        {
            "name": "workspace-volume",
            "hostPath": {"path": make_workspace_host_path("acme"), "type": "DirectoryOrCreate"},
        },
    ]
    assert mounts == [
        {"name": "home-volume", "mountPath": "/kubeai/home"},
        {"name": "workspace-volume", "mountPath": "/kubeai/workspace"},
    ]


# ── build_kubeai_env_vars (框架键优先于 extra) ────────────────────────────────


def test_build_kubeai_env_vars_framework_keys_override_extra() -> None:
    env = build_kubeai_env_vars(extra={"HOME": "/tmp", "FOO": "bar"})
    # 框架键 HOME 覆盖 extra; 用户键 FOO 保留.
    assert env["HOME"] == "/kubeai/home"
    assert env["FOO"] == "bar"
    assert env["KUBEAI_ROOT_PATH"] == "/kubeai"
    assert env["KUBEAI_HOME_PATH"] == "/kubeai/home"
    assert env["KUBEAI_WORKSPACE_PATH"] == "/kubeai/workspace"
    assert env["SHELL"] == "/bin/bash"


def test_build_kubeai_env_vars_env_id_optional() -> None:
    assert "KUBEAI_ENV_ID" not in build_kubeai_env_vars()
    assert build_kubeai_env_vars(env_id="abc-123")["KUBEAI_ENV_ID"] == "abc-123"


# ── build_chown_init_container (busybox, root, chown 1000:100) ──────────────


def test_build_chown_init_container_runs_root_and_chowns() -> None:
    mounts = [{"name": "home-volume", "mountPath": "/kubeai/home"}]
    init = build_chown_init_container(name="inference-init", volume_mounts=mounts)
    assert init["image"] == settings.BUSYBOX_IMAGE
    assert init["securityContext"] == {"runAsUser": 0, "runAsGroup": 0}
    assert init["volumeMounts"] == mounts
    assert "chown -R 1000:100 /kubeai" in init["args"][0]


# ── build_deployment (initContainer / 卷 / envFrom / imagePullSecrets / securityContext) ──


def test_build_deployment_without_extras_is_minimal() -> None:
    body = build_deployment(name="svc", namespace=_NAMESPACE, image="img", container_port=8000)
    pod_spec = body["spec"]["template"]["spec"]
    assert pod_spec["containers"][0]["image"] == "img"
    assert "initContainers" not in pod_spec
    assert "volumes" not in pod_spec
    assert "imagePullSecrets" not in pod_spec
    assert "envFrom" not in pod_spec["containers"][0]
    assert "securityContext" not in pod_spec["containers"][0]


def test_build_deployment_with_security_context_and_initcontainer() -> None:
    init = {"name": "inference-init", "image": "busybox:1.36"}
    body = build_deployment(
        name="svc",
        namespace=_NAMESPACE,
        image="img",
        container_port=8000,
        init_containers=[init],
        volumes=[{"name": "home-volume", "hostPath": {"path": "/data", "type": "DirectoryOrCreate"}}],
        volume_mounts=[{"name": "home-volume", "mountPath": "/kubeai/home"}],
        image_pull_secrets=["registry-pull-secret"],
        security_context={"runAsUser": 1000, "runAsGroup": 100, "runAsNonRoot": True},
    )
    pod_spec = body["spec"]["template"]["spec"]
    assert pod_spec["initContainers"] == [init]
    assert pod_spec["imagePullSecrets"] == [{"name": "registry-pull-secret"}]
    container = pod_spec["containers"][0]
    assert container["securityContext"] == {"runAsUser": 1000, "runAsGroup": 100, "runAsNonRoot": True}
    assert container["volumeMounts"] == [{"name": "home-volume", "mountPath": "/kubeai/home"}]


# ── build_scaled_object (GPU/DCGM 触发器) ─────────────────────────────────────


def test_scaled_object_cpu_trigger_uses_native_cpu() -> None:
    obj = build_scaled_object(
        name="svc-autoscaler",
        namespace=_NAMESPACE,
        deploy_name="svc",
        min_replicas=1,
        max_replicas=3,
        metric_type="cpu",
        metric_value=70,
    )
    trigger = obj["spec"]["triggers"][0]
    assert trigger["type"] == "cpu"
    assert trigger["metricType"] == "Utilization"


def test_scaled_object_gpu_trigger_uses_dcgm_promql_scoped_to_deployment() -> None:
    obj = build_scaled_object(
        name="svc-autoscaler",
        namespace=_NAMESPACE,
        deploy_name="svc",
        min_replicas=0,
        max_replicas=4,
        metric_type="gpu",
        metric_value=60,
    )
    trigger = obj["spec"]["triggers"][0]
    assert trigger["type"] == "prometheus"
    assert trigger["metadata"]["metricName"] == "gpu_utilization"
    query = trigger["metadata"]["query"]
    # 必须按 namespace + Deployment 标签过滤 (而非全集群平均).
    assert f'namespace="{_NAMESPACE}"' in query
    assert 'app_kubernetes_io_name="svc"' in query
    assert "DCGM_FI_DEV_GPU_UTIL" in query
    assert trigger["metadata"]["threshold"] == "60"
