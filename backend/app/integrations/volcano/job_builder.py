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
    hyperparameters: dict[str, str] | None = None,
    priority: str = "normal",
    dataset_pvc_name: str | None = None,
    dataset_mount_path: str | None = None,
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
                    "template": {
                        "spec": {
                            "containers": [
                                {
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
                            ],
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
                    },
                }
            ],
        },
    }
