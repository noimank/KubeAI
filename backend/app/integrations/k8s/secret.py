import base64
import logging

from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.core.config import settings
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

S3_SECRET_NAME = "s3-credentials"
REGISTRY_PULL_SECRET_NAME = "registry-pull-secret"


def _encode_secret_data(data: dict[str, str]) -> dict[str, str]:
    return {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}


async def create_secret(
    namespace: str, name: str, data: dict[str, str], *, secret_type: str = "Opaque"
) -> client.V1Secret:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    secret = client.V1Secret(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        type=secret_type,
        data=_encode_secret_data(data),
    )

    try:
        await core_v1.create_namespaced_secret(namespace=namespace, body=secret)
        logger.info("Created Secret %s in namespace %s", name, namespace)
        return secret
    except ApiException as e:
        if e.status == 409:
            await core_v1.replace_namespaced_secret(name=name, namespace=namespace, body=secret)
            logger.info("Updated Secret %s in namespace %s", name, namespace)
            return secret
        raise


async def delete_secret(namespace: str, name: str) -> None:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        await core_v1.delete_namespaced_secret(name=name, namespace=namespace)
        logger.info("Deleted Secret %s from namespace %s", name, namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise


async def get_secret(namespace: str, name: str) -> dict[str, str] | None:
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]

    try:
        secret = await core_v1.read_namespaced_secret(name=name, namespace=namespace)
        decoded = {}
        if secret.data:
            for k, v in secret.data.items():
                decoded[k] = base64.b64decode(v).decode()
        return decoded
    except ApiException as e:
        if e.status == 404:
            return None
        raise


async def create_s3_credentials_secret(namespace: str) -> client.V1Secret:
    """Create S3 credentials secret for tenant namespace (MinIO access)."""
    return await create_secret(
        namespace=namespace,
        name=S3_SECRET_NAME,
        data={
            "AWS_ACCESS_KEY_ID": settings.MINIO_ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": settings.MINIO_SECRET_KEY,
            "AWS_DEFAULT_REGION": "us-east-1",
        },
    )


async def delete_s3_credentials_secret(namespace: str) -> None:
    """Delete S3 credentials secret from tenant namespace."""
    await delete_secret(namespace=namespace, name=S3_SECRET_NAME)


async def ensure_s3_credentials_secret(namespace: str) -> None:
    """Ensure S3 credentials secret exists in tenant namespace."""
    await create_s3_credentials_secret(namespace)


def make_secret_name(tenant_name: str, credential_name: str) -> str:
    return f"credential-{sanitize_k8s_name(tenant_name)}-{sanitize_k8s_name(credential_name)}"


async def ensure_registry_pull_secret(namespace: str) -> str:
    """Ensure a docker-registry pull secret exists in the tenant namespace using Harbor credentials."""
    from app.core.events import get_harbor_client

    harbor_client = get_harbor_client()
    docker_config = harbor_client.make_harbor_dockerconfig()
    docker_config_json = docker_config.get("config.json", "{}")

    await create_secret(
        namespace=namespace,
        name=REGISTRY_PULL_SECRET_NAME,
        data={".dockerconfigjson": docker_config_json},
        secret_type="kubernetes.io/dockerconfigjson",
    )
    return REGISTRY_PULL_SECRET_NAME
