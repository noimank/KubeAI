from typing import Any


def build_canary_inferenceservice(
    *,
    stable_service: dict[str, Any],
    canary_storage_uri: str,
    canary_model_format: str = "custom",
    resources: dict[str, Any] | None = None,
    replicas: int = 1,
    env_vars: dict[str, str] | None = None,
) -> dict[str, Any]:
    stable_meta = stable_service.get("metadata", {})
    stable_name = stable_meta.get("name", "")
    namespace = stable_meta.get("namespace", "")

    min_replicas = replicas
    max_replicas = replicas

    predictor: dict[str, Any] = {
        "minReplicas": min_replicas,
        "maxReplicas": max_replicas,
        "model": {
            "modelFormat": {"name": canary_model_format},
            "storageUri": canary_storage_uri,
        },
    }

    if resources:
        predictor["model"]["resources"] = resources

    manifest: dict[str, Any] = {
        "apiVersion": "serving.kserve.io/v1beta1",
        "kind": "InferenceService",
        "metadata": {
            "name": f"{stable_name}-canary",
            "namespace": namespace,
            "annotations": {
                "serving.kserve.io/s3-secret": "s3-credentials",
                "sidecar.istio.io/inject": "false",
                "kubeai.io/canary-for": stable_name,
            },
        },
        "spec": {
            "predictor": predictor,
        },
    }

    if env_vars:
        manifest["spec"]["predictor"]["model"]["env"] = [{"name": k, "value": v} for k, v in env_vars.items()]

    return manifest
