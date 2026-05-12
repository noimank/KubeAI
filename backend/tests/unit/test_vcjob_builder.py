from app.integrations.volcano.job_builder import build_vcjob


class TestBuildVcjobSingle:
    def test_single_task_default(self):
        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=2,
            gpu_mode="exclusive",
            job_id="abc-123",
        )

        assert result["metadata"]["name"] == "test-job"
        assert result["metadata"]["namespace"] == "kubeai-default"
        assert result["spec"]["minAvailable"] == 1
        assert len(result["spec"]["tasks"]) == 1
        assert result["spec"]["tasks"][0]["name"] == "trainer"
        assert result["spec"]["tasks"][0]["replicas"] == 1
        assert "plugins" not in result["spec"]

    def test_single_task_no_gpu(self):
        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="python:3.12",
            command="python run.py",
            cpu="2",
            memory="4Gi",
            gpu_count=0,
            gpu_mode="shared",
            job_id="abc-456",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        assert "nvidia.com/gpu" not in container["resources"]["limits"]

    def test_single_task_with_dataset(self):
        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="abc-789",
            dataset_pvc_name="dataset-pvc",
            dataset_mount_path="/data/datasets/my-set/v1",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        assert container["volumeMounts"][0]["mountPath"] == "/data/datasets/my-set/v1"
        pod_spec = result["spec"]["tasks"][0]["template"]["spec"]
        assert pod_spec["volumes"][0]["persistentVolumeClaim"]["claimName"] == "dataset-pvc"

    def test_single_task_with_hyperparameters(self):
        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="abc-hp",
            hyperparameters={"lr": "0.01", "epochs": "100"},
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "HP_LR" in env_names
        assert "HP_EPOCHS" in env_names

    def test_priority_classes(self):
        for priority in ("low", "normal", "high"):
            result = build_vcjob(
                vcjob_name=f"test-{priority}",
                namespace="kubeai-default",
                image_ref="pytorch:2.1",
                command="python train.py",
                cpu="4",
                memory="8Gi",
                gpu_count=1,
                gpu_mode="exclusive",
                job_id="abc-pr",
                priority=priority,
            )
            assert result["spec"]["priorityClass"] == priority

    def test_single_task_no_dist_env_vars(self):
        result = build_vcjob(
            vcjob_name="single-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="single-env",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "MASTER_ADDR" not in env_names
        assert "RANK" not in env_names
        assert "WORLD_SIZE" not in env_names


class TestBuildVcjobDistributed:
    def test_distributed_no_plugins(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=2,
            gpu_mode="exclusive",
            job_id="dist-123",
            worker_count=4,
        )

        assert result["spec"]["minAvailable"] == 4
        assert "plugins" not in result["spec"]

    def test_distributed_tasks_structure(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="dist-456",
            worker_count=3,
        )

        tasks = result["spec"]["tasks"]
        assert len(tasks) == 3

        assert tasks[0]["name"] == "master"
        assert tasks[0]["replicas"] == 1
        assert tasks[0]["policies"] == [{"event": "TaskCompleted", "action": "CompleteJob"}]

        assert tasks[1]["name"] == "worker-1"
        assert tasks[1]["replicas"] == 1

        assert tasks[2]["name"] == "worker-2"
        assert tasks[2]["replicas"] == 1

    def test_distributed_master_env_vars(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=2,
            gpu_mode="exclusive",
            job_id="dist-master",
            worker_count=4,
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        env = {e["name"]: e["value"] for e in container["env"]}

        assert env["MASTER_ADDR"] == "dist-job-master-0.dist-job"
        assert env["MASTER_PORT"] == "23456"
        assert env["WORLD_SIZE"] == "4"
        assert env["RANK"] == "0"

    def test_distributed_worker_env_vars(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=2,
            gpu_mode="exclusive",
            job_id="dist-worker",
            worker_count=4,
        )

        tasks = result["spec"]["tasks"]

        worker_1_env = {e["name"]: e["value"] for e in tasks[1]["template"]["spec"]["containers"][0]["env"]}
        assert worker_1_env["RANK"] == "1"
        assert worker_1_env["MASTER_ADDR"] == "dist-job-master-0.dist-job"
        assert worker_1_env["WORLD_SIZE"] == "4"

        worker_3_env = {e["name"]: e["value"] for e in tasks[3]["template"]["spec"]["containers"][0]["env"]}
        assert worker_3_env["RANK"] == "3"

    def test_distributed_env_vars_per_task_unique(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="dist-uniq",
            worker_count=3,
        )

        ranks = []
        for task in result["spec"]["tasks"]:
            env = {e["name"]: e["value"] for e in task["template"]["spec"]["containers"][0]["env"]}
            ranks.append(env["RANK"])

        assert ranks == ["0", "1", "2"]

    def test_distributed_same_resources_per_task(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="8",
            memory="16Gi",
            gpu_count=4,
            gpu_mode="exclusive",
            job_id="dist-res",
            worker_count=2,
        )

        for task in result["spec"]["tasks"]:
            container = task["template"]["spec"]["containers"][0]
            resources = container["resources"]
            assert resources["limits"]["cpu"] == "8"
            assert resources["limits"]["memory"] == "16Gi"
            assert resources["limits"]["nvidia.com/gpu"] == "4"

    def test_distributed_with_dataset_pvc(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="dist-pvc",
            worker_count=3,
            dataset_pvc_name="my-dataset-pvc",
            dataset_mount_path="/data/my-set",
        )

        for task in result["spec"]["tasks"]:
            container = task["template"]["spec"]["containers"][0]
            assert container["volumeMounts"][0]["mountPath"] == "/data/my-set"
            volumes = task["template"]["spec"]["volumes"]
            assert volumes[0]["persistentVolumeClaim"]["claimName"] == "my-dataset-pvc"

    def test_distributed_priority(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="dist-pr",
            worker_count=2,
            priority="high",
        )
        assert result["spec"]["priorityClass"] == "high"

    def test_worker_count_1_no_dist_env(self):
        result = build_vcjob(
            vcjob_name="single-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="single-no-dist",
            worker_count=1,
        )

        assert "plugins" not in result["spec"]
        assert result["spec"]["minAvailable"] == 1
        assert len(result["spec"]["tasks"]) == 1


class TestBuildVcjobHostPath:
    def test_workspace_host_path_volume(self):
        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="ws-123",
            workspace_host_path="/data/kubeai/tenant/my-team/workspace",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        mounts = container["volumeMounts"]
        ws_mount = next(m for m in mounts if m["mountPath"] == "/workspace")
        assert ws_mount["name"] == "workspace-volume"

        volumes = result["spec"]["tasks"][0]["template"]["spec"]["volumes"]
        ws_vol = next(v for v in volumes if v["name"] == "workspace-volume")
        assert ws_vol["hostPath"]["path"] == "/data/kubeai/tenant/my-team/workspace"
        assert ws_vol["hostPath"]["type"] == "DirectoryOrCreate"

        env = {e["name"]: e["value"] for e in container["env"]}
        assert env["KUBEAI_WORKSPACE_PATH"] == "/workspace"

    def test_user_home_host_path_volume(self):
        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="home-123",
            user_home_host_path="/data/kubeai/users/johndoe",
            username="johndoe",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        mounts = container["volumeMounts"]
        home_mount = next(m for m in mounts if m["mountPath"] == "/home/johndoe")
        assert home_mount["name"] == "home-volume"

        volumes = result["spec"]["tasks"][0]["template"]["spec"]["volumes"]
        home_vol = next(v for v in volumes if v["name"] == "home-volume")
        assert home_vol["hostPath"]["path"] == "/data/kubeai/users/johndoe"

        env = {e["name"]: e["value"] for e in container["env"]}
        assert env["KUBEAI_HOME_PATH"] == "/home/johndoe"

    def test_both_host_paths(self):
        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="both-123",
            workspace_host_path="/data/kubeai/tenant/team/workspace",
            user_home_host_path="/data/kubeai/users/alice",
            username="alice",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        mount_paths = [m["mountPath"] for m in container["volumeMounts"]]
        assert "/workspace" in mount_paths
        assert "/home/alice" in mount_paths

    def test_no_host_path_when_not_provided(self):
        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="no-hp-123",
        )

        volumes = result["spec"]["tasks"][0]["template"]["spec"]["volumes"]
        vol_names = [v["name"] for v in volumes]
        assert "workspace-volume" not in vol_names
        assert "home-volume" not in vol_names

    def test_distributed_host_paths_all_workers(self):
        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="dist-ws",
            worker_count=3,
            workspace_host_path="/data/kubeai/tenant/team/workspace",
            user_home_host_path="/data/kubeai/users/bob",
            username="bob",
        )

        for task in result["spec"]["tasks"]:
            container = task["template"]["spec"]["containers"][0]
            mount_paths = [m["mountPath"] for m in container["volumeMounts"]]
            assert "/workspace" in mount_paths
            assert "/home/bob" in mount_paths
