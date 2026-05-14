from typing import Any


def build_inferenceservice(
    *,
    name: str,
    namespace: str,
    storage_uri: str,
    model_format: str = "custom",
    resources: dict[str, Any] | None = None,
    replicas: int = 1,
    env_vars: dict[str, str] | None = None,
) -> dict[str, Any]:
    predictor: dict[str, Any] = {
        "minReplicas": replicas,
        "maxReplicas": replicas,
        "model": {
            "modelFormat": {"name": model_format},
            "storageUri": storage_uri,
        },
    }

    if resources:
        predictor["model"]["resources"] = resources

    manifest: dict[str, Any] = {
        "apiVersion": "serving.kserve.io/v1beta1",
        "kind": "InferenceService",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "annotations": {
                "serving.kserve.io/s3-secret": "s3-credentials",
                "sidecar.istio.io/inject": "false",
            },
        },
        "spec": {
            "predictor": predictor,
        },
    }

    if env_vars:
        manifest["spec"]["predictor"]["model"]["env"] = [{"name": k, "value": v} for k, v in env_vars.items()]

    return manifest


def build_resource_spec(cpu: str, memory: str, gpu_count: int) -> dict[str, Any]:
    resources: dict[str, Any] = {
        "requests": {"cpu": cpu, "memory": memory},
        "limits": {"cpu": cpu, "memory": memory},
    }
    if gpu_count > 0:
        gpu_key = "nvidia.com/gpu"
        resources["requests"][gpu_key] = str(gpu_count)
        resources["limits"][gpu_key] = str(gpu_count)
    return resources
