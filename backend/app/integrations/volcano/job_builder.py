import copy
from typing import Any


def build_vcjob(
    *,
    vcjob_name: str,
    namespace: str,
    image_ref: str,
    command: str,
    cpu: str,
    memory: str,
    gpu_count: int,
    gpu_mode: str,
    job_id: str,
    worker_count: int = 1,
    hyperparameters: dict[str, str] | None = None,
    priority: str = "normal",
    dataset_pvc_name: str | None = None,
    dataset_mount_path: str | None = None,
    metrics_port: int | None = None,
) -> dict[str, Any]:
    env: list[dict[str, str]] = [
        {"name": "KUBEAI_JOB_ID", "value": job_id},
    ]
    if dataset_mount_path:
        env.append({"name": "KUBEAI_DATASET_PATH", "value": dataset_mount_path})
    if hyperparameters:
        for key, value in hyperparameters.items():
            env.append({"name": f"HP_{key.upper()}", "value": value})

    resources: dict[str, Any] = {
        "requests": {"cpu": cpu, "memory": memory},
        "limits": {"cpu": cpu, "memory": memory},
    }
    if gpu_count > 0:
        gpu_key = "nvidia.com/gpu"
        resources["requests"][gpu_key] = str(gpu_count)
        resources["limits"][gpu_key] = str(gpu_count)

    priority_class_map = {"low": "low", "normal": "normal", "high": "high"}

    container: dict[str, Any] = {
        "name": "trainer",
        "image": image_ref,
        "command": ["/bin/sh", "-c"],
        "args": [command],
        "resources": resources,
        "env": env,
        **(
            {
                "volumeMounts": [
                    {
                        "name": "dataset-volume",
                        "mountPath": dataset_mount_path,
                        "readOnly": True,
                    }
                ]
            }
            if dataset_pvc_name and dataset_mount_path
            else {}
        ),
    }

    if metrics_port is not None:
        container["ports"] = [{"containerPort": metrics_port}]

    pod_spec: dict[str, Any] = {
        "containers": [container],
        "volumes": (
            [
                {
                    "name": "dataset-volume",
                    "persistentVolumeClaim": {"claimName": dataset_pvc_name},
                }
            ]
            if dataset_pvc_name
            else []
        ),
        "restartPolicy": "OnFailure",
    }

    if worker_count > 1:
        return _build_distributed_vcjob(
            vcjob_name=vcjob_name,
            namespace=namespace,
            pod_spec=pod_spec,
            worker_count=worker_count,
            priority=priority_class_map.get(priority, "normal"),
        )

    return {
        "apiVersion": "batch.volcano.sh/v1alpha1",
        "kind": "Job",
        "metadata": {
            "name": vcjob_name,
            "namespace": namespace,
        },
        "spec": {
            "minAvailable": 1,
            "schedulerName": "volcano",
            "queue": "default",
            "maxRetry": 2,
            "priorityClass": priority_class_map.get(priority, "normal"),
            "policies": [{"event": "PodEvicted", "action": "RestartJob"}],
            "tasks": [
                {
                    "replicas": 1,
                    "name": "trainer",
                    "policies": [{"event": "TaskCompleted", "action": "CompleteJob"}],
                    "template": {"spec": pod_spec},
                }
            ],
        },
    }


def _build_distributed_vcjob(
    *,
    vcjob_name: str,
    namespace: str,
    pod_spec: dict[str, Any],
    worker_count: int,
    priority: str,
) -> dict[str, Any]:
    master_addr = f"{vcjob_name}-master-0.{vcjob_name}"
    dist_env_base = [
        {"name": "MASTER_ADDR", "value": master_addr},
        {"name": "MASTER_PORT", "value": "23456"},
        {"name": "WORLD_SIZE", "value": str(worker_count)},
    ]

    tasks: list[dict[str, Any]] = [
        {
            "replicas": 1,
            "name": "master",
            "policies": [{"event": "TaskCompleted", "action": "CompleteJob"}],
            "template": {"spec": _inject_env(pod_spec, [*dist_env_base, {"name": "RANK", "value": "0"}])},
        }
    ]

    for i in range(1, worker_count):
        tasks.append(
            {
                "replicas": 1,
                "name": f"worker-{i}",
                "template": {"spec": _inject_env(pod_spec, [*dist_env_base, {"name": "RANK", "value": str(i)}])},
            }
        )

    return {
        "apiVersion": "batch.volcano.sh/v1alpha1",
        "kind": "Job",
        "metadata": {
            "name": vcjob_name,
            "namespace": namespace,
        },
        "spec": {
            "minAvailable": worker_count,
            "schedulerName": "volcano",
            "queue": "default",
            "maxRetry": 2,
            "priorityClass": priority,
            "policies": [{"event": "PodEvicted", "action": "RestartJob"}],
            "tasks": tasks,
        },
    }


def _inject_env(pod_spec: dict[str, Any], extra_env: list[dict[str, str]]) -> dict[str, Any]:
    spec = copy.deepcopy(pod_spec)
    spec["containers"][0]["env"].extend(extra_env)
    return spec
