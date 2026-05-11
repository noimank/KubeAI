import logging

logger = logging.getLogger(__name__)

K8S_NAMESPACE_PREFIX = "kubeai-"


def sanitize_k8s_name(name: str, max_length: int = 63) -> str:
    result = "".join(c if c.isalnum() or c == "-" else "-" for c in name.lower()).strip("-")
    while "--" in result:
        result = result.replace("--", "-")
    return result[:max_length].strip("-") or "default"
