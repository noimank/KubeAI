import logging

from kubernetes import client
from kubernetes.client.rest import ApiException

from app.integrations.base import with_retry
from app.integrations.k8s.client import get_k8s_clients

logger = logging.getLogger(__name__)

POLICY_NAME = "tenant-isolation"

ALLOWED_NAMESPACES = [
    "kube-system",
    "kubeai-platform",
]


def build_tenant_network_policy(namespace: str) -> client.V1NetworkPolicy:
    ns_selectors = []
    for ns in [namespace, *ALLOWED_NAMESPACES]:
        ns_selectors.append(
            client.V1LabelSelector(
                match_labels={"kubernetes.io/metadata.name": ns},
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
                    _from=ns_selectors,
                ),
            ],
            egress=[
                client.V1NetworkPolicyEgressRule(
                    to=ns_selectors,
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


@with_retry(max_retries=3)
def create_tenant_network_policy(namespace: str) -> client.V1NetworkPolicy:
    k8s = get_k8s_clients()
    networking_v1: client.NetworkingV1Api = k8s["networking_v1"]

    policy = build_tenant_network_policy(namespace)

    try:
        networking_v1.create_namespaced_network_policy(
            namespace=namespace,
            body=policy,
        )
        logger.info("Created NetworkPolicy %s in namespace %s", POLICY_NAME, namespace)
        return policy
    except ApiException as e:
        if e.status == 409:
            logger.info("NetworkPolicy %s already exists in %s", POLICY_NAME, namespace)
            return policy
        raise


@with_retry(max_retries=3)
def delete_network_policy(namespace: str, name: str = POLICY_NAME) -> None:
    k8s = get_k8s_clients()
    networking_v1: client.NetworkingV1Api = k8s["networking_v1"]

    try:
        networking_v1.delete_namespaced_network_policy(
            name=name,
            namespace=namespace,
        )
        logger.info("Deleted NetworkPolicy %s from namespace %s", name, namespace)
    except ApiException as e:
        if e.status == 404:
            return
        raise
