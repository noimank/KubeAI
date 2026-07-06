from typing import Any

from app.core.config import settings


def build_scaled_object(
    *,
    name: str,
    namespace: str,
    deploy_name: str,
    min_replicas: int,
    max_replicas: int,
    metric_type: str,
    metric_value: int,
    cooldown_period: int = 300,
    polling_interval: int = 30,
) -> dict[str, Any]:
    triggers: list[dict[str, Any]] = []
    if metric_type == "cpu":
        triggers.append(
            {
                "type": "cpu",
                "metadata": {"value": str(metric_value)},
                "metricType": "Utilization",
            }
        )
    else:
        # metric_type == "gpu": 按 DCGM GPU 利用率伸缩.
        # dcgm-exporter 开启 enablePodLabels, DCGM_FI_DEV_GPU_UTIL 带 namespace 与
        # pod 标签 (app.kubernetes.io/name 经 Prometheus 规范化为 app_kubernetes_io_name).
        # avg 聚合该 Deployment 全部 GPU/Pod; threshold = 目标 GPU 利用率%.
        triggers.append(
            {
                "type": "prometheus",
                "metadata": {
                    "serverAddress": settings.PROMETHEUS_URL,
                    "metricName": "gpu_utilization",
                    "threshold": str(metric_value),
                    "query": (
                        f'avg(DCGM_FI_DEV_GPU_UTIL{{namespace="{namespace}",app_kubernetes_io_name="{deploy_name}"}})'
                    ),
                },
            }
        )

    return {
        "apiVersion": "keda.sh/v1alpha1",
        "kind": "ScaledObject",
        "metadata": {
            "name": name,
            "namespace": namespace,
        },
        "spec": {
            "scaleTargetRef": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": deploy_name,
            },
            "minReplicaCount": min_replicas,
            "maxReplicaCount": max_replicas,
            "cooldownPeriod": cooldown_period,
            "pollingInterval": polling_interval,
            "triggers": triggers,
        },
    }
