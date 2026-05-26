from app.integrations.base import sanitize_k8s_name

KUBEAI_DATA_DIR = "/data/kubeai"


def make_dataset_host_path(tenant_name: str, dataset_name: str, version_number: int) -> str:
    return f"{KUBEAI_DATA_DIR}/datasets/{sanitize_k8s_name(tenant_name)}/{sanitize_k8s_name(dataset_name)}/v{version_number}"


def make_workspace_host_path(tenant_name: str) -> str:
    return f"{KUBEAI_DATA_DIR}/tenant/{sanitize_k8s_name(tenant_name)}/workspace"


def make_user_home_host_path(username: str) -> str:
    return f"{KUBEAI_DATA_DIR}/users/{sanitize_k8s_name(username)}"
