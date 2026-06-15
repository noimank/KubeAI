"""
K8s Dev Pod Manager — native Pod/Service lifecycle for development environments.

Path-based routing via APISIX Admin API (not ApisixRoute CRD). Each env gets
``/devenv/{uuid_hex}`` as its path prefix, served through the company's existing
APISIX gateway.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from kubernetes_asyncio import client
from kubernetes_asyncio.client.rest import ApiException

from app.core.config import settings
from app.integrations.k8s.client import get_k8s_clients

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEV_ENV_LABEL_KEY = "kubeai.io/dev-env-id"
DEV_ENV_PORT = 8888
DEV_ENV_PATH_PREFIX = "/devenv"

_RESOURCE_LABEL = {
    "app.kubernetes.io/managed-by": "kubeai",
    "app.kubernetes.io/component": "dev-environment",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def _env_id_hex(env_id: uuid.UUID) -> str:
    """UUID as 32-char hex (no dashes) — DNS-safe, URL-safe."""
    return env_id.hex


def _resource_name(env_id: uuid.UUID) -> str:
    return f"devenv-{_env_id_hex(env_id)}"


def dev_path(env_id: uuid.UUID) -> str:
    """The URL path prefix for an environment: ``/devenv/<hex>``."""
    return f"{DEV_ENV_PATH_PREFIX}/{_env_id_hex(env_id)}"


def dev_id_from_path(path: str) -> uuid.UUID | None:
    """Extract env UUID from a URL path like ``/devenv/<hex>/...``."""
    if not path.startswith(DEV_ENV_PATH_PREFIX + "/"):
        return None
    hex_part = path[len(DEV_ENV_PATH_PREFIX) + 1 :].split("/")[0]
    try:
        return uuid.UUID(hex=hex_part)
    except (ValueError, AttributeError):
        return None


def dev_access_url(env_id: uuid.UUID) -> str:
    """Full external URL for a dev environment — derived from ``FRONTEND_URL``."""
    host = settings.FRONTEND_URL.rstrip("/") if settings.FRONTEND_URL else "http://localhost:3000"
    from urllib.parse import urlparse

    parsed = urlparse(host)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}{dev_path(env_id)}/"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _env_labels(env_id: uuid.UUID) -> dict[str, str]:
    return {**_RESOURCE_LABEL, DEV_ENV_LABEL_KEY: str(env_id)}


def _to_v1_env_vars(env_vars: dict[str, str] | None) -> list[client.V1EnvVar]:
    if not env_vars:
        return []
    return [client.V1EnvVar(name=k, value=v) for k, v in env_vars.items()]


def _v1_volume(v: dict[str, Any]) -> client.V1Volume:
    hp = v.get("hostPath", v.get("host_path"))
    if hp:
        return client.V1Volume(
            name=v["name"],
            host_path=client.V1HostPathVolumeSource(path=hp["path"], type=hp.get("type", "DirectoryOrCreate")),
        )
    pvc = v.get("persistentVolumeClaim", v.get("persistent_volume_claim"))
    if pvc:
        return client.V1Volume(
            name=v["name"],
            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=pvc["claimName"]),
        )
    return client.V1Volume(name=v["name"])


def _v1_volume_mount(vm: dict[str, Any]) -> client.V1VolumeMount:
    return client.V1VolumeMount(
        name=vm["name"],
        mount_path=vm.get("mountPath", vm.get("mount_path")),
        sub_path=vm.get("subPath", vm.get("sub_path")),
        read_only=vm.get("readOnly", vm.get("read_only")),
    )


def _estimate_last_activity(pod: client.V1Pod) -> str:
    now = datetime.now(UTC)
    candidates: list[datetime] = []
    if pod.metadata and pod.metadata.creation_timestamp:
        candidates.append(pod.metadata.creation_timestamp)
    if pod.status:
        for cond in pod.status.conditions or []:
            if cond.type == "Ready" and cond.last_transition_time:
                candidates.append(cond.last_transition_time)
        for cs in pod.status.container_statuses or []:
            if cs.state and cs.state.running and cs.state.running.started_at:
                candidates.append(cs.state.running.started_at)
    if not candidates:
        return now.isoformat()
    latest = max(candidates)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    return latest.isoformat()


# ---------------------------------------------------------------------------
# Pod builder
# ---------------------------------------------------------------------------


def build_dev_pod(
    *,
    env_id: uuid.UUID,
    namespace: str,
    image: str,
    environment_type: str | None,
    cpu: str,
    memory: str,
    gpu_count: int,
    env_vars: dict[str, str] | None,
    volumes: list[dict[str, Any]],
    volume_mounts: list[dict[str, Any]],
    image_pull_secret: str | None,
    node_selector: dict[str, str] | None = None,
) -> client.V1Pod:
    name = _resource_name(env_id)
    labels = _env_labels(env_id)
    path = dev_path(env_id)

    resources = client.V1ResourceRequirements(
        requests={"cpu": cpu, "memory": memory},
        limits={"cpu": cpu, "memory": memory},
    )
    if gpu_count > 0:
        gpu_str = str(gpu_count)
        resources.requests["nvidia.com/gpu"] = gpu_str
        resources.limits["nvidia.com/gpu"] = gpu_str

    container = client.V1Container(
        name=name,
        image=image,
        working_dir="/kubeai/home",  # Open directly at user's home directory
        resources=resources,
        env=_to_v1_env_vars(env_vars),
        volume_mounts=[_v1_volume_mount(vm) for vm in volume_mounts],
        ports=[client.V1ContainerPort(container_port=DEV_ENV_PORT, name="http")],
        security_context=client.V1SecurityContext(run_as_user=1000, run_as_group=100, run_as_non_root=True),
    )

    _apply_native_entrypoint(container, environment_type, path)

    # initContainer: chown all hostPath volume mounts to UID 1000.
    # hostPath directories created by kubelet are owned by root; without this the
    # non-root container (run_as_user=1000) cannot write to /kubeai/home etc.
    init_volume_mounts = [_v1_volume_mount(vm) for vm in volume_mounts]
    init_container = client.V1Container(
        name=f"{name}-init",
        image=settings.BUSYBOX_IMAGE,
        command=["sh", "-c"],
        args=[
            # chown everything under /kubeai — harmless if sub-dirs don't exist yet
            "chown -R 1000:100 /kubeai 2>/dev/null; echo 'init done'"
        ],
        volume_mounts=init_volume_mounts,
        resources=client.V1ResourceRequirements(
            requests={"cpu": "50m", "memory": "32Mi"},
            limits={"cpu": "100m", "memory": "64Mi"},
        ),
        security_context=client.V1SecurityContext(run_as_user=0, run_as_group=0),
    )

    pod_spec = client.V1PodSpec(
        init_containers=[init_container],
        containers=[container],
        volumes=[_v1_volume(v) for v in volumes],
        restart_policy="Never",
        node_selector=node_selector or {},
        automount_service_account_token=False,
    )
    if image_pull_secret:
        pod_spec.image_pull_secrets = [client.V1LocalObjectReference(name=image_pull_secret)]

    return client.V1Pod(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        spec=pod_spec,
    )


def _apply_native_entrypoint(container: client.V1Container, environment_type: str | None, base_url: str) -> None:
    """Set native cmd/args per environment type.  All internal auth disabled.

    ``base_url`` is the path prefix (e.g. ``/devenv/<hex>``) without trailing
    slash.  Each app uses its own sub-path mechanism:

    - Jupyter: ``--ServerApp.base_url`` — serves at the full prefixed path
    - VS Code: code-server has NO sub-path flag → APISIX ``proxy-rewrite`` strips prefix
    - RStudio: ``--www-root-path`` — serves at the full prefixed path
    """
    base = f"{base_url}/"

    if environment_type == "jupyter":
        # Jupyter serves at the full path; APISIX does NOT strip the prefix.
        container.command = ["jupyter", "lab"]
        container.args = [
            "--ServerApp.token=''",
            "--ServerApp.password=''",
            "--ServerApp.ip=0.0.0.0",
            f"--ServerApp.port={DEV_ENV_PORT}",
            f"--ServerApp.base_url={base}",
            "--ServerApp.allow_origin='*'",
            "--ServerApp.disable_check_xsrf=True",
            # Open file browser at user's persistent home directory
            "--ServerApp.root_dir=/kubeai/home",
            "--ServerApp.notebook_dir=/kubeai/home",
        ]
    elif environment_type == "vscode":
        # code-server has NO sub-path flag.  APISIX proxy-rewrite strips the
        # /devenv/<hex> prefix, so code-server runs at root.
        container.command = ["code-server"]
        container.args = [
            "--auth",
            "none",
            "--bind-addr",
            f"0.0.0.0:{DEV_ENV_PORT}",
            "--disable-telemetry",
            "--user-data-dir",
            "/kubeai/home/.code-server",
        ]
    elif environment_type == "rstudio":
        # RStudio --www-root-path tells it the prefix added by a reverse proxy.
        # APISIX does NOT strip the prefix.
        container.command = ["rserver"]
        container.args = [
            f"--www-port={DEV_ENV_PORT}",
            f"--www-root-path={base}",
            "--auth-none=1",
            "--server-daemonize=0",
            # Persist RStudio session data in user's home directory
            "--server-data-dir=/kubeai/home/.rstudio",
        ]
    else:
        # Default: Jupyter (same as above)
        container.command = ["jupyter", "lab"]
        container.args = [
            "--ServerApp.token=''",
            "--ServerApp.password=''",
            "--ServerApp.ip=0.0.0.0",
            f"--ServerApp.port={DEV_ENV_PORT}",
            f"--ServerApp.base_url={base}",
            "--ServerApp.allow_origin='*'",
            "--ServerApp.disable_check_xsrf=True",
            "--ServerApp.root_dir=/kubeai/home",
            "--ServerApp.notebook_dir=/kubeai/home",
        ]


# ---------------------------------------------------------------------------
# Service builder
# ---------------------------------------------------------------------------


def build_dev_service(env_id: uuid.UUID, namespace: str) -> client.V1Service:
    name = _resource_name(env_id)
    return client.V1Service(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=_env_labels(env_id)),
        spec=client.V1ServiceSpec(
            selector={DEV_ENV_LABEL_KEY: str(env_id)},
            ports=[client.V1ServicePort(port=DEV_ENV_PORT, target_port=DEV_ENV_PORT, name="http")],
            type="ClusterIP",
        ),
    )


# ---------------------------------------------------------------------------
# APISIX Admin API — route management
# ---------------------------------------------------------------------------


def _build_apisix_route_payload(
    *,
    env_id: uuid.UUID,
    namespace: str,
    environment_type: str | None = None,
) -> dict[str, Any]:
    """Build an APISIX Admin API route payload for a dev environment.

    Direct Admin API call — no CRD, no ingress-controller.

    **Token delivery**: ``$cookie_xxx`` NGINX variables do NOT resolve in the
    ``forward-auth`` plugin.  We rely exclusively on ``request_headers: ["Cookie"]``
    to forward the browser's raw ``Cookie`` header to the auth backend.  The
    backend reads ``kubeai_access_token`` directly from the forwarded cookie.

    ``proxy-rewrite`` is only used for VS Code (code-server has no sub-path
    flag).  Jupyter (``--ServerApp.base_url``) and RStudio (``--www-root-path``)
    serve at the full prefixed path.
    """
    name = _resource_name(env_id)
    path = dev_path(env_id)
    route_id = _env_id_hex(env_id)

    # NO $cookie_xxx — it does NOT resolve in forward-auth.  Cookie header
    # forwarding via request_headers is the only reliable mechanism.
    auth_uri = f"{settings.KUBEAI_BACKEND_INTERNAL_URL}/api/dev-environments/auth-check?env_id={env_id}"

    # K8s service FQDN — APISIX runs in the kubeai namespace but the dev
    # pod Service is in the tenant namespace.
    upstream_node = f"{name}.{namespace}.svc.cluster.local:{DEV_ENV_PORT}"

    plugins: dict[str, Any] = {
        "forward-auth": {
            "_meta": {"disable": False},
            "uri": auth_uri,
            # request_headers forwards the browser's raw headers to the
            # auth-check backend.  Cookie is the only reliable way to pass
            # the JWT — extra_headers/$cookie_xxx does NOT work in APISIX.
            "request_headers": ["Cookie"],
            "upstream_headers": ["X-KubeAI-User"],
        },
    }

    # Only VS Code needs proxy-rewrite — code-server has no sub-path flag.
    if environment_type == "vscode":
        plugins["proxy-rewrite"] = {
            "regex_uri": [f"^{path}/(.*)", "/$1"],
        }

    return {
        "id": route_id,
        "name": name,
        "status": 1,
        "uri": f"{path}/*",
        "host": _dev_host(),
        "priority": 100,
        "enable_websocket": True,  # Required by VS Code / Jupyter for terminal & workbench
        "plugins": plugins,
        "upstream": {
            "type": "roundrobin",
            "scheme": "http",
            "nodes": {upstream_node: 1},
            "timeout": {
                "connect": 15,
                "send": 3600,
                "read": 3600,
            },
        },
    }


async def _apisix_create_route(env_id: uuid.UUID, namespace: str, environment_type: str | None = None) -> None:
    """Push a route directly to APISIX Admin API using a fresh connection."""
    payload = _build_apisix_route_payload(env_id=env_id, namespace=namespace, environment_type=environment_type)
    route_id = _env_id_hex(env_id)

    async with httpx.AsyncClient(
        base_url=settings.KUBEAI_APISIX_ADMIN_URL.rstrip("/"),
        headers={"X-API-KEY": settings.KUBEAI_APISIX_ADMIN_KEY},
        timeout=httpx.Timeout(10.0),
        http2=False,
    ) as client:
        resp = await client.put(f"/apisix/admin/routes/{route_id}", json=payload)
        resp.raise_for_status()
        if resp.status_code in (200, 201):
            logger.info("apisix_route_created", route_id=route_id)


async def _apisix_delete_route(env_id: uuid.UUID) -> None:
    """Delete a route from APISIX Admin API by ID."""
    route_id = _env_id_hex(env_id)

    async with httpx.AsyncClient(
        base_url=settings.KUBEAI_APISIX_ADMIN_URL.rstrip("/"),
        headers={"X-API-KEY": settings.KUBEAI_APISIX_ADMIN_KEY},
        timeout=httpx.Timeout(10.0),
        http2=False,
    ) as client:
        resp = await client.delete(f"/apisix/admin/routes/{route_id}")
        logger.info("apisix_route_deleted", route_id=route_id, status=resp.status_code)


def _dev_host() -> str:
    """APISIX host filter — derived from FRONTEND_URL hostname."""
    from urllib.parse import urlparse

    if settings.FRONTEND_URL and "://" in settings.FRONTEND_URL:
        return urlparse(settings.FRONTEND_URL).hostname or "localhost"
    return "localhost"


# ---------------------------------------------------------------------------
# Lifecycle operations
# ---------------------------------------------------------------------------


class DevPodManager:
    """Manages Pod + Service + APISIX route lifecycle for a single dev environment."""

    async def create(self, **kwargs: Any) -> None:
        k8s = await get_k8s_clients()
        core_v1: client.CoreV1Api = k8s["core_v1"]

        env_id: uuid.UUID = kwargs["env_id"]
        namespace: str = kwargs["namespace"]
        name = _resource_name(env_id)

        pod = build_dev_pod(**kwargs)
        svc = build_dev_service(env_id, namespace)

        logger.info("dev_pod_creating", name=name, namespace=namespace)

        try:
            await core_v1.create_namespaced_service(namespace=namespace, body=svc)
        except ApiException as e:
            if e.status != 409:
                raise

        try:
            await core_v1.create_namespaced_pod(namespace=namespace, body=pod)
        except ApiException as e:
            if e.status == 409:
                await core_v1.delete_namespaced_pod(name=name, namespace=namespace)
                await core_v1.create_namespaced_pod(namespace=namespace, body=pod)
            else:
                raise

        # Push the route to APISIX after the pod is running — non-fatal,
        # the pod works even if this call fails (retry or recreate will fix it).
        try:
            await _apisix_create_route(
                env_id=env_id,
                namespace=namespace,
                environment_type=kwargs.get("environment_type"),
            )
        except Exception:
            logger.warning("apisix_route_create_failed", name=name, exc_info=True)

        logger.info("dev_pod_created", name=name)

    async def delete(self, env_id: uuid.UUID, namespace: str) -> None:
        k8s = await get_k8s_clients()
        core_v1: client.CoreV1Api = k8s["core_v1"]
        name = _resource_name(env_id)

        # Delete APISIX route first
        try:
            await _apisix_delete_route(env_id)
        except Exception:
            logger.warning("apisix_route_delete_error", name=name)

        for kind, fn in (
            ("pod", lambda: core_v1.delete_namespaced_pod(name=name, namespace=namespace)),
            ("service", lambda: core_v1.delete_namespaced_service(name=name, namespace=namespace)),
        ):
            try:
                await fn()
            except ApiException as e:
                if e.status != 404:
                    logger.warning("dev_resource_delete_failed", kind=kind, name=name, error=str(e))

    async def get_pod(self, env_id: uuid.UUID, namespace: str) -> client.V1Pod | None:
        try:
            k8s = await get_k8s_clients()
            pod: client.V1Pod | None = await k8s["core_v1"].read_namespaced_pod(
                name=_resource_name(env_id), namespace=namespace
            )
            return pod
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    async def get_pod_last_activity(self, env_id: uuid.UUID, namespace: str) -> str | None:
        pod = await self.get_pod(env_id, namespace)
        return _estimate_last_activity(pod) if pod else None

    async def stop_server(self, env_id: uuid.UUID, namespace: str) -> None:
        """Delete pod only; keep Service + APISIX route for restart."""
        try:
            k8s = await get_k8s_clients()
            await k8s["core_v1"].delete_namespaced_pod(name=_resource_name(env_id), namespace=namespace)
        except ApiException as e:
            if e.status != 404:
                raise


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_dev_pod_manager: DevPodManager | None = None


def get_dev_pod_manager() -> DevPodManager:
    global _dev_pod_manager
    if _dev_pod_manager is None:
        _dev_pod_manager = DevPodManager()
    return _dev_pod_manager
