from typing import Any


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
        triggers.append(
            {
                "type": "prometheus",
                "metadata": {
                    "serverAddress": "http://prometheus.monitoring.svc.cluster.local:9090",
                    "query": (f'sum(rate(istio_requests_total{{destination_service=~"{deploy_name}.*"}}[1m]))'),
                    "threshold": str(metric_value),
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
