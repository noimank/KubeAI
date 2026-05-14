from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.integrations.k8s.client import get_k8s_clients

if TYPE_CHECKING:
    from kubernetes_asyncio.client import V1Job

logger = logging.getLogger(__name__)


def build_upload_job(
    *,
    namespace: str,
    job_name: str,
    workspace_host_path: str,
    source_paths: list[str],
    minio_endpoint: str,
    minio_access_key: str,
    minio_secret_key: str,
    minio_bucket: str,
    target_path: str,
    active_deadline_seconds: int = 600,
) -> V1Job:
    from kubernetes_asyncio import client as k8s_client

    copy_commands = "\n".join(
        f"mc cp --recursive /workspace/{src} kubeai/$MINIO_BUCKET/$TARGET_PATH/" for src in source_paths
    )

    job = k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=job_name, labels={"app.kubernetes.io/managed-by": "kubeai", "kubeai.io/type": "upload"}
        ),
        spec=k8s_client.V1JobSpec(
            ttl_seconds_after_finished=300,
            active_deadline_seconds=active_deadline_seconds,
            backoff_limit=2,
            template=k8s_client.V1PodTemplateSpec(
                spec=k8s_client.V1PodSpec(
                    containers=[
                        k8s_client.V1Container(
                            name="uploader",
                            image="minio/mc:latest",
                            resources=k8s_client.V1ResourceRequirements(
                                requests={"cpu": "100m", "memory": "128Mi"},
                                limits={"cpu": "500m", "memory": "256Mi"},
                            ),
                            command=["/bin/sh", "-c"],
                            args=[
                                f"mc alias set kubeai $MINIO_ENDPOINT $MINIO_ACCESS_KEY $MINIO_SECRET_KEY\n{copy_commands}"
                            ],
                            env=[
                                k8s_client.V1EnvVar(name="MINIO_ENDPOINT", value=minio_endpoint),
                                k8s_client.V1EnvVar(name="MINIO_ACCESS_KEY", value=minio_access_key),
                                k8s_client.V1EnvVar(name="MINIO_SECRET_KEY", value=minio_secret_key),
                                k8s_client.V1EnvVar(name="MINIO_BUCKET", value=minio_bucket),
                                k8s_client.V1EnvVar(name="TARGET_PATH", value=target_path),
                            ],
                            volume_mounts=[
                                k8s_client.V1VolumeMount(name="workspace", mount_path="/workspace"),
                            ],
                        )
                    ],
                    volumes=[
                        k8s_client.V1Volume(
                            name="workspace",
                            host_path=k8s_client.V1HostPathVolumeSource(
                                path=workspace_host_path, type="DirectoryOrCreate"
                            ),
                        )
                    ],
                    restart_policy="OnFailure",
                )
            ),
        ),
    )
    return job


async def create_upload_job(namespace: str, job: V1Job) -> V1Job:
    k8s = await get_k8s_clients()
    batch_v1 = k8s["batch_v1"]
    result = await batch_v1.create_namespaced_job(namespace=namespace, body=job)
    return result  # type: ignore[no-any-return]


async def get_upload_job_status(namespace: str, job_name: str) -> dict[str, str | int | bool]:
    k8s = await get_k8s_clients()
    batch_v1 = k8s["batch_v1"]
    try:
        job = await batch_v1.read_namespaced_job(name=job_name, namespace=namespace)
    except Exception:
        return {"status": "not_found", "succeeded": False, "failed": False}

    conditions = job.status.conditions or []
    for cond in conditions:
        if cond.type == "Complete" and cond.status == "True":
            return {"status": "completed", "succeeded": True, "failed": False}
        if cond.type == "Failed" and cond.status == "True":
            return {"status": "failed", "succeeded": False, "failed": True, "message": cond.message or ""}

    return {"status": "running", "succeeded": False, "failed": False}
