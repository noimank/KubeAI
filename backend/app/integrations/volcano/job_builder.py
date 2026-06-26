import copy
import uuid
from typing import Any

from app.core.config import settings
from app.integrations.k8s.tensorboard import tensorboard_path

# 容器内统一挂载根路径, 与开发环境保持一致
KUBEAI_CONTAINER_ROOT = "/kubeai"

# TensorBoard sidecar 与 trainer 共享的日志目录
TENSORBOARD_CONTAINER_LOG_DIR = f"{KUBEAI_CONTAINER_ROOT}/tensorboard"


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
    worker_count: int = 1,
    hyperparameters: dict[str, str] | None = None,
    priority: str = "normal",
    dataset_host_path: str | None = None,
    dataset_mount_path: str | None = None,
    workspace_host_path: str | None = None,
    user_home_host_path: str | None = None,
    username: str | None = None,
    mlflow_tracking_uri: str | None = None,
    mlflow_experiment_name: str | None = None,
    mlflow_run_id: str | None = None,
    tensorboard_enabled: bool = False,
) -> dict[str, Any]:
    env: list[dict[str, str]] = [
        {"name": "KUBEAI_JOB_ID", "value": job_id},
        # Python 在非 TTY 容器里 stdout/stderr 默认全缓冲 (8KB), 训练日志会积在内存
        # 直到进程退出才落盘 → kubectl logs / 平台 WebSocket 日志流长时间为空.
        # 设为 unbuffered 让日志实时可见, 对非 Python 任务无副作用.
        {"name": "PYTHONUNBUFFERED", "value": "1"},
    ]
    if dataset_mount_path:
        env.append({"name": "KUBEAI_DATASET_PATH", "value": dataset_mount_path})
    if workspace_host_path:
        env.append({"name": "KUBEAI_WORKSPACE_PATH", "value": f"{KUBEAI_CONTAINER_ROOT}/workspace"})
    if user_home_host_path and username:
        env.append({"name": "KUBEAI_HOME_PATH", "value": f"{KUBEAI_CONTAINER_ROOT}/home"})
    if hyperparameters:
        for key, value in hyperparameters.items():
            env.append({"name": f"HP_{key.upper()}", "value": value})
    if mlflow_tracking_uri:
        env.append({"name": "MLFLOW_TRACKING_URI", "value": mlflow_tracking_uri})
    if mlflow_experiment_name:
        # 训练脚本据此把 run 落到平台预建的 experiment.
        env.append({"name": "MLFLOW_EXPERIMENT_NAME", "value": mlflow_experiment_name})
    if mlflow_run_id:
        # 平台预创建的 run_id: 训练脚本须 mlflow.start_run(run_id=...) 恢复它, 形成 job↔run
        # 强绑定 (Volcano 重试 resume 同一 run, 不再产生多 run).
        env.append({"name": "MLFLOW_RUN_ID", "value": mlflow_run_id})
    if tensorboard_enabled:
        # 训练脚本应将 tfevents 写入此目录, sidecar 自动读取.
        env.append({"name": "TENSORBOARD_LOG_DIR", "value": TENSORBOARD_CONTAINER_LOG_DIR})

    resources: dict[str, Any] = {
        "requests": {"cpu": cpu, "memory": memory},
        "limits": {"cpu": cpu, "memory": memory},
    }
    if gpu_count > 0:
        gpu_key = "nvidia.com/gpu"
        resources["requests"][gpu_key] = str(gpu_count)
        resources["limits"][gpu_key] = str(gpu_count)

    priority_class_map = {"low": "low", "normal": "normal", "high": "high"}

    mounts: list[dict[str, Any]] = []
    if dataset_host_path and dataset_mount_path:
        mounts.append({"name": "dataset-volume", "mountPath": dataset_mount_path, "readOnly": True})
    if workspace_host_path:
        mounts.append({"name": "workspace-volume", "mountPath": f"{KUBEAI_CONTAINER_ROOT}/workspace"})
    if user_home_host_path and username:
        mounts.append({"name": "home-volume", "mountPath": f"{KUBEAI_CONTAINER_ROOT}/home"})
    if tensorboard_enabled:
        # trainer 挂载共享卷以写入 tfevents; sidecar 同卷读取.
        mounts.append({"name": "tensorboard-logs", "mountPath": TENSORBOARD_CONTAINER_LOG_DIR})

    container: dict[str, Any] = {
        "name": "trainer",
        "image": image_ref,
        "command": ["/bin/sh", "-c"],
        "args": [command],
        "workingDir": f"{KUBEAI_CONTAINER_ROOT}/home",
        "resources": resources,
        "env": env,
        **({"volumeMounts": mounts} if mounts else {}),
    }

    init_containers: list[dict[str, Any]] = []
    if tensorboard_enabled:
        # K8s ≥1.28 原生 sidecar (initContainer + restartPolicy=Always): kubelet 在主容器
        # 启动前拉起 sidecar, 并在主容器全部退出后自动终止它. 这样 trainer 正常结束后
        # Pod 才能进入 Succeeded, Volcano task 完成并释放 GPU. 若用普通容器作 sidecar,
        # tensorboard 常驻会导致 Pod 永不完成 → 任务永远停在 RUNNING + GPU 泄漏.
        #
        # --path_prefix 让 TensorBoard 在 /tensorboard/<hex> 子路径下生成正确的资源 URL,
        # 配合 APISIX 原样转发 (不做 proxy-rewrite 剥前缀).
        init_containers.append(
            {
                "name": "tensorboard",
                "image": settings.TENSORBOARD_IMAGE,
                "command": [
                    "tensorboard",
                    f"--logdir={TENSORBOARD_CONTAINER_LOG_DIR}",
                    "--host=0.0.0.0",
                    f"--port={settings.TENSORBOARD_PORT}",
                    f"--path_prefix={tensorboard_path(uuid.UUID(job_id))}",
                    "--noassets",
                ],
                "restartPolicy": "Always",
                "resources": {
                    "requests": {"cpu": "100m", "memory": "256Mi"},
                    "limits": {"cpu": "500m", "memory": "512Mi"},
                },
                "ports": [{"containerPort": settings.TENSORBOARD_PORT, "name": "tb"}],
                "volumeMounts": [{"name": "tensorboard-logs", "mountPath": TENSORBOARD_CONTAINER_LOG_DIR}],
                "securityContext": {"runAsUser": 1000, "runAsGroup": 1000},
            }
        )

    volumes: list[dict[str, Any]] = []
    if dataset_host_path:
        volumes.append({"name": "dataset-volume", "hostPath": {"path": dataset_host_path, "type": "DirectoryOrCreate"}})
    if workspace_host_path:
        volumes.append(
            {"name": "workspace-volume", "hostPath": {"path": workspace_host_path, "type": "DirectoryOrCreate"}}
        )
    if user_home_host_path:
        volumes.append({"name": "home-volume", "hostPath": {"path": user_home_host_path, "type": "DirectoryOrCreate"}})
    if tensorboard_enabled:
        # emptyDir: trainer 与 sidecar 同 Pod 共享, Pod 重启时日志归零 (VCJob 重试语义).
        volumes.append({"name": "tensorboard-logs", "emptyDir": {}})

    pod_spec: dict[str, Any] = {
        "containers": [container],
        "volumes": volumes,
        # restartPolicy=Never 确保容器崩溃后 Pod 进入 Failed 阶段,
        # 让 Volcano 的 task maxRetry 和 job maxRetry 正常工作,
        # 而不是由 Kubelet 无限重启容器永远不 fail
        "restartPolicy": "Never",
    }
    if init_containers:
        pod_spec["initContainers"] = init_containers

    if worker_count > 1:
        return _build_distributed_vcjob(
            vcjob_name=vcjob_name,
            namespace=namespace,
            pod_spec=pod_spec,
            worker_count=worker_count,
            priority=priority_class_map.get(priority, "normal"),
        )

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
            "ttlSecondsAfterFinished": 86400,
            "priorityClass": priority_class_map.get(priority, "normal"),
            "policies": [{"event": "PodEvicted", "action": "RestartJob"}],
            "tasks": [
                {
                    "replicas": 1,
                    # task name 统一为 "master", 与分布式场景 (worker_count>1) 保持一致.
                    # 这样 TensorBoard Service selector (volcano.sh/task-name=master)
                    # 在单 master 训练时也能匹配, 不依赖 worker_count.
                    "name": "master",
                    "maxRetry": 3,
                    "policies": [{"event": "TaskCompleted", "action": "CompleteJob"}],
                    "template": {"spec": pod_spec},
                }
            ],
        },
    }


def _build_distributed_vcjob(
    *,
    vcjob_name: str,
    namespace: str,
    pod_spec: dict[str, Any],
    worker_count: int,
    priority: str,
) -> dict[str, Any]:
    master_addr = f"{vcjob_name}-master-0.{vcjob_name}"
    dist_env_base = [
        {"name": "MASTER_ADDR", "value": master_addr},
        {"name": "MASTER_PORT", "value": "23456"},
        {"name": "WORLD_SIZE", "value": str(worker_count)},
    ]

    # 分布式训练只在 master task 注入 TensorBoard sidecar.
    # master_pod_spec 含 sidecar (initContainer) + 共享卷;
    # worker_pod_spec 剥离 sidecar 与 tensorboard-logs 卷, 无 6006 端口.
    master_pod_spec = pod_spec
    worker_pod_spec = _strip_tensorboard_from_pod_spec(copy.deepcopy(pod_spec))

    tasks: list[dict[str, Any]] = [
        {
            "replicas": 1,
            "name": "master",
            "maxRetry": 3,
            "policies": [{"event": "TaskCompleted", "action": "CompleteJob"}],
            "template": {"spec": _inject_env(master_pod_spec, [*dist_env_base, {"name": "RANK", "value": "0"}])},
        }
    ]

    for i in range(1, worker_count):
        tasks.append(
            {
                "replicas": 1,
                "name": f"worker-{i}",
                "maxRetry": 3,
                "template": {"spec": _inject_env(worker_pod_spec, [*dist_env_base, {"name": "RANK", "value": str(i)}])},
            }
        )

    return {
        "apiVersion": "batch.volcano.sh/v1alpha1",
        "kind": "Job",
        "metadata": {
            "name": vcjob_name,
            "namespace": namespace,
        },
        "spec": {
            "minAvailable": worker_count,
            "schedulerName": "volcano",
            "queue": "default",
            "maxRetry": 2,
            "ttlSecondsAfterFinished": 86400,
            "priorityClass": priority,
            "policies": [{"event": "PodEvicted", "action": "RestartJob"}],
            "tasks": tasks,
        },
    }


def _strip_tensorboard_from_pod_spec(pod_spec: dict[str, Any]) -> dict[str, Any]:
    """Remove TensorBoard sidecar declarations from a pod spec (distributed workers).

    Workers get no sidecar: drop ``initContainers`` (the only one is the TB
    sidecar) and the shared ``tensorboard-logs`` volume, plus its mount on the
    trainer (an orphaned volumeMount would make the pod un-schedulable). The
    trainer container itself is otherwise untouched.
    """
    pod_spec.pop("initContainers", None)
    pod_spec["volumes"] = [v for v in pod_spec.get("volumes", []) if v.get("name") != "tensorboard-logs"]
    for container in pod_spec.get("containers", []):
        if "volumeMounts" in container:
            container["volumeMounts"] = [m for m in container["volumeMounts"] if m.get("name") != "tensorboard-logs"]
    return pod_spec


def _inject_env(pod_spec: dict[str, Any], extra_env: list[dict[str, str]]) -> dict[str, Any]:
    spec = copy.deepcopy(pod_spec)
    spec["containers"][0]["env"].extend(extra_env)
    return spec
