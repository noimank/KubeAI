import logging

from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.core.config import settings
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

POLICY_NAME = "tenant-isolation"

DEFAULT_ALLOWED_NAMESPACES = [
    "kube-system",
    "apisix",  # APISIX gateway — must be able to reach dev-environment pods in tenant namespaces
]
ALLOWED_NAMESPACES = DEFAULT_ALLOWED_NAMESPACES


def get_allowed_namespaces() -> list[str]:
    namespaces = [settings.K8S_PLATFORM_NAMESPACE, *DEFAULT_ALLOWED_NAMESPACES]
    return list(dict.fromkeys(ns.strip() for ns in namespaces if ns.strip()))


def build_tenant_network_policy(namespace: str) -> client.V1NetworkPolicy:
    ns_peers = []
    for ns in [namespace, *get_allowed_namespaces()]:
        ns_peers.append(
            client.V1NetworkPolicyPeer(
                namespace_selector=client.V1LabelSelector(
                    match_labels={"kubernetes.io/metadata.name": ns},
                ),
            )
        )

    return client.V1NetworkPolicy(
        api_version="networking.k8s.io/v1",
        kind="NetworkPolicy",
        metadata=client.V1ObjectMeta(name=POLICY_NAME, namespace=namespace),
        spec=client.V1NetworkPolicySpec(
            pod_selector=client.V1LabelSelector(),
            policy_types=["Ingress", "Egress"],
            ingress=[
                client.V1NetworkPolicyIngressRule(
                    _from=ns_peers,
                ),
            ],
            egress=[
                client.V1NetworkPolicyEgressRule(
                    to=ns_peers,
                ),
                client.V1NetworkPolicyEgressRule(
                    to=[
                        client.V1NetworkPolicyPeer(
                            ip_block=client.V1IPBlock(cidr="0.0.0.0/0"),
                        ),
                    ],
                    ports=[
                        client.V1NetworkPolicyPort(
                            protocol="TCP",
                            port=53,
                        ),
                        client.V1NetworkPolicyPort(
                            protocol="UDP",
                            port=53,
                        ),
                    ],
                ),
            ],
        ),
    )


async def create_tenant_network_policy(namespace: str) -> client.V1NetworkPolicy:
    k8s = await get_k8s_clients()
    networking_v1: client.NetworkingV1Api = k8s["networking_v1"]

    policy = build_tenant_network_policy(namespace)

    try:
        await networking_v1.create_namespaced_network_policy(
            namespace=namespace,
            body=policy,
        )
        logger.info("Created NetworkPolicy %s in namespace %s", POLICY_NAME, namespace)
        return policy
    except ApiException as e:
        if e.status == 409:
            await networking_v1.replace_namespaced_network_policy(
                name=POLICY_NAME,
                namespace=namespace,
                body=policy,
            )
            logger.info("Updated NetworkPolicy %s in namespace %s", POLICY_NAME, namespace)
            return policy
        raise


async def delete_network_policy(namespace: str, name: str = POLICY_NAME) -> None:
    k8s = await get_k8s_clients()
    networking_v1: client.NetworkingV1Api = k8s["networking_v1"]

    try:
        await networking_v1.delete_namespaced_network_policy(
            name=name,
            namespace=namespace,
        )
        logger.info("Deleted NetworkPolicy %s from namespace %s", name, namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise
