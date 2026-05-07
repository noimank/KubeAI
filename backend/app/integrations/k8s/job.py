import logging

from kubernetes import client  # type: ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

from app.integrations.base import with_retry
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

KANIKO_IMAGE = "gcr.io/kaniko-project/executor:latest"
HARBOR_SECRET_NAME = "harbor-credentials"
KANIKO_CPU_REQUEST = "500m"
KANIKO_MEMORY_REQUEST = "1Gi"
KANIKO_CPU_LIMIT = "2"
KANIKO_MEMORY_LIMIT = "4Gi"


@with_retry(max_retries=2)
def create_configmap(namespace: str, name: str, data: dict[str, str]) -> client.V1ConfigMap:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    cm = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        data=data,
    )

    try:
        core_v1.create_namespaced_config_map(namespace=namespace, body=cm)
        logger.info("Created ConfigMap %s in namespace %s", name, namespace)
        return cm
    except ApiException as e:
        if e.status == 409:
            core_v1.replace_namespaced_config_map(name=name, namespace=namespace, body=cm)
            logger.info("Updated ConfigMap %s in namespace %s", name, namespace)
            return cm
        raise


@with_retry(max_retries=2)
def delete_configmap(namespace: str, name: str) -> None:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        core_v1.delete_namespaced_config_map(name=name, namespace=namespace)
        logger.info("Deleted ConfigMap %s from namespace %s", name, namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise


def create_build_job(
    namespace: str,
    job_name: str,
    dockerfile_configmap: str,
    destination: str,
    harbor_url: str,
    kaniko_image: str = KANIKO_IMAGE,
) -> client.V1Job:
    kaniko_args = [
        "--dockerfile=Dockerfile",
        "--context=dir:///workspace",
        f"--destination={destination}",
        "--verbosity=info",
    ]
    if harbor_url.startswith("https://"):
        kaniko_args.append("--skip-tls-verify")
    else:
        kaniko_args.append("--insecure")

    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name, namespace=namespace),
        spec=client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=3600,
            template=client.V1PodTemplateSpec(
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name="kaniko",
                            image=kaniko_image,
                            resources=client.V1ResourceRequirements(
                                requests={"cpu": KANIKO_CPU_REQUEST, "memory": KANIKO_MEMORY_REQUEST},
                                limits={"cpu": KANIKO_CPU_LIMIT, "memory": KANIKO_MEMORY_LIMIT},
                            ),
                            args=kaniko_args,
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="dockerfile",
                                    mount_path="/workspace/Dockerfile",
                                    sub_path="Dockerfile",
                                ),
                                client.V1VolumeMount(
                                    name="harbor-secret",
                                    mount_path="/kaniko/.docker",
                                    read_only=True,
                                ),
                            ],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="dockerfile",
                            config_map=client.V1ConfigMapVolumeSource(name=dockerfile_configmap),
                        ),
                        client.V1Volume(
                            name="harbor-secret",
                            secret=client.V1SecretVolumeSource(secret_name=HARBOR_SECRET_NAME),
                        ),
                    ],
                )
            ),
        ),
    )
    return job


@with_retry(max_retries=2)
def submit_job(namespace: str, job: client.V1Job) -> client.V1Job:
    k8s = get_k8s_clients()
    batch_v1: client.BatchV1Api = k8s["batch_v1"]

    result = batch_v1.create_namespaced_job(namespace=namespace, body=job)
    logger.info("Created Job %s in namespace %s", job.metadata.name, namespace)
    return result


def get_job_status(namespace: str, job_name: str) -> dict[str, str | bool]:
    k8s = get_k8s_clients()
    batch_v1: client.BatchV1Api = k8s["batch_v1"]

    try:
        job = batch_v1.read_namespaced_job(name=job_name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return {"exists": False, "status": "unknown"}
        raise

    status = job.status
    if status.succeeded:
        return {"exists": True, "status": "succeeded", "active": False}
    if status.failed:
        return {"exists": True, "status": "failed", "active": False}
    if status.active:
        return {"exists": True, "status": "running", "active": True}
    return {"exists": True, "status": "pending", "active": False}


def get_job_logs(namespace: str, job_name: str) -> str:
    k8s = get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    pods = core_v1.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"job-name={job_name}",
    )
    if not pods.items:
        return ""

    pod_name = pods.items[0].metadata.name
    try:
        logs = core_v1.read_namespaced_pod_log(name=pod_name, namespace=namespace)
        return logs
    except ApiException:
        return ""


@with_retry(max_retries=2)
def delete_job(namespace: str, job_name: str) -> None:
    k8s = get_k8s_clients()
    batch_v1: client.BatchV1Api = k8s["batch_v1"]

    try:
        batch_v1.delete_namespaced_job(
            name=job_name,
            namespace=namespace,
            propagation_policy="Background",
        )
        logger.info("Deleted Job %s from namespace %s", job_name, namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise


def make_job_name(image_id: str) -> str:
    return f"image-build-{image_id[:8]}"


def make_configmap_name(image_id: str) -> str:
    return f"dockerfile-{image_id[:8]}"
