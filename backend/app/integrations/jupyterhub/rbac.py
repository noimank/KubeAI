import structlog
from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.core.config import settings
from app.integrations.k8s.client import get_k8s_clients

logger = structlog.get_logger(__name__)

ROLE_NAME = "kubeai-jupyterhub-tenant-spawner"
ROLE_BINDING_NAME = "kubeai-jupyterhub-tenant-spawner"


def _hub_service_account_name() -> str:
    return settings.JUPYTERHUB_HUB_SERVICE_ACCOUNT.strip()


def build_jupyterhub_tenant_role(namespace: str) -> client.V1Role:
    return client.V1Role(
        api_version="rbac.authorization.k8s.io/v1",
        kind="Role",
        metadata=client.V1ObjectMeta(name=ROLE_NAME, namespace=namespace),
        rules=[
            client.V1PolicyRule(
                api_groups=[""],
                resources=["pods", "persistentvolumeclaims", "secrets", "services"],
                verbs=["get", "watch", "list", "create", "delete"],
            ),
            client.V1PolicyRule(
                api_groups=[""],
                resources=["events"],
                verbs=["get", "watch", "list"],
            ),
        ],
    )


def build_jupyterhub_tenant_role_binding(namespace: str) -> client.V1RoleBinding | None:
    service_account_name = _hub_service_account_name()
    if not service_account_name:
        return None

    return client.V1RoleBinding(
        api_version="rbac.authorization.k8s.io/v1",
        kind="RoleBinding",
        metadata=client.V1ObjectMeta(name=ROLE_BINDING_NAME, namespace=namespace),
        subjects=[
            client.RbacV1Subject(
                kind="ServiceAccount",
                name=service_account_name,
                namespace=settings.K8S_PLATFORM_NAMESPACE,
            )
        ],
        role_ref=client.V1RoleRef(
            api_group="rbac.authorization.k8s.io",
            kind="Role",
            name=ROLE_NAME,
        ),
    )


async def ensure_jupyterhub_tenant_rbac(namespace: str) -> None:
    role_binding = build_jupyterhub_tenant_role_binding(namespace)
    if role_binding is None:
        logger.info("jupyterhub_rbac_skipped_no_service_account")
        return

    k8s = await get_k8s_clients()
    rbac_v1: client.RbacAuthorizationV1Api = k8s["rbac_v1"]

    role = build_jupyterhub_tenant_role(namespace)
    try:
        await rbac_v1.create_namespaced_role(namespace=namespace, body=role)
        logger.info("jupyterhub_role_created", namespace=namespace)
    except ApiException as e:
        if e.status != 409:
            raise
        await rbac_v1.replace_namespaced_role(name=ROLE_NAME, namespace=namespace, body=role)
        logger.info("jupyterhub_role_updated", namespace=namespace)

    try:
        await rbac_v1.create_namespaced_role_binding(namespace=namespace, body=role_binding)
        logger.info("jupyterhub_role_binding_created", namespace=namespace)
    except ApiException as e:
        if e.status != 409:
            raise
        await rbac_v1.replace_namespaced_role_binding(name=ROLE_BINDING_NAME, namespace=namespace, body=role_binding)
        logger.info("jupyterhub_role_binding_updated", namespace=namespace)


async def delete_jupyterhub_tenant_rbac(namespace: str) -> None:
    if not _hub_service_account_name():
        return

    k8s = await get_k8s_clients()
    rbac_v1: client.RbacAuthorizationV1Api = k8s["rbac_v1"]

    try:
        await rbac_v1.delete_namespaced_role_binding(name=ROLE_BINDING_NAME, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        await rbac_v1.delete_namespaced_role(name=ROLE_NAME, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            raise
